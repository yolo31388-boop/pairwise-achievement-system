"""成就点数与称号系统。

规则：
- 成就条件实时校验，失去条件时进度/完成状态回退，但已领取的点数保留。
- 点数按 pve/pvp/life/explore 分类，角色绑定，分类商店独立。
- 称号仅在装备后提供属性，全局同时只能装备一个。
- 隐藏成就未完成时只给模糊提示，完成后展示完整条件。
- 成就完成即自动发放奖励并标记已领取，未完成/可领取/已领取分区查看。
- 删除角色清除其点数；账号级领取台账阻止删号重建重复刷取同一成就。
"""
from dataclasses import dataclass, field

CATEGORIES = ("pve", "pvp", "life", "explore")

# 数值越小越好的条件键，达成判定为 actual <= target
_LOWER_IS_BETTER = frozenset({"rank", "arena_rank"})

_CONDITION_LABELS = {
    "rank": "排名进入前{value}名",
    "arena_rank": "竞技场排名进入前{value}名",
    "level": "等级达到{value}级",
    "kills": "累计击杀{value}个目标",
    "wins": "累计获胜{value}场",
    "count": "累计完成{value}次",
    "location": "在{value}",
    "action": "完成{value}",
    "item": "获得物品：{value}",
    "quest": "完成任务：{value}",
}

_VAGUE_HINT = "在某处做某事"
DEFAULT_CHARACTER = "default"


@dataclass
class Achievement:
    aid: str
    name: str
    category: str  # pve/pvp/life/explore
    points: int
    condition: dict
    hidden: bool = False
    hint: str = ""
    title: str = ""  # 完成时授予的称号 tid


@dataclass
class Title:
    tid: str
    name: str
    stats: dict = field(default_factory=dict)
    equipped: bool = False


@dataclass
class ShopItem:
    item_id: str
    name: str
    cost: int


class Shop:
    """单一分类的点数商店，只能消费对应分类的点数。"""

    def __init__(self, category: str):
        self.category = category
        self.items: dict[str, ShopItem] = {}

    def add_item(self, item_id: str, name: str, cost: int) -> None:
        self.items[item_id] = ShopItem(item_id, name, cost)

    def get_item(self, item_id: str) -> ShopItem | None:
        return self.items.get(item_id)


class AchievementSystem:
    def __init__(self):
        self.achievements: dict[str, Achievement] = {}
        self.completed: dict[str, bool] = {}
        self.progress: dict[str, int] = {}  # aid -> 0~100
        self.points: dict[str, int] = {c: 0 for c in CATEGORIES}
        self.titles: dict[str, Title] = {}
        self.claimed: set[str] = set()  # 领取台账键：aid 或 character_id_aid
        self.shops: dict[str, Shop] = {c: Shop(c) for c in CATEGORIES}
        self.equipped_title: str | None = None

        # 角色绑定数据
        self.character_points: dict[str, dict[str, int]] = {}
        self.character_claimed: dict[str, set[str]] = {}
        # 账号级防刷台账：同一成就无论在哪个角色上只能领取一次
        self.account_claimed: set[str] = set()

    # ---------- 条件实时校验 ----------

    def _compare(self, actual, target, lower_is_better: bool) -> bool:
        if lower_is_better:
            return actual is not None and actual <= target
        return actual is not None and actual >= target

    def _condition_ratio(self, key: str, actual, target) -> float:
        if not isinstance(target, (int, float)) or target == 0:
            return 1.0 if self._match_key(key, target, actual) else 0.0
        if key in _LOWER_IS_BETTER:
            ratio = target / actual if actual else 0.0
        else:
            ratio = actual / target if actual is not None else 0.0
        return max(0.0, min(1.0, ratio))

    def _match_key(self, key: str, target, actual) -> bool:
        if isinstance(target, dict) and "op" in target:
            op = target["op"]
            value = target["value"]
            if actual is None:
                return False
            if op == ">=":
                return actual >= value
            if op == "<=":
                return actual <= value
            if op == "==":
                return actual == value
            if op == "!=":
                return actual != value
            if op == ">":
                return actual > value
            if op == "<":
                return actual < value
            return False
        if isinstance(actual, (list, tuple, set, frozenset)):
            return target in actual
        if key in _LOWER_IS_BETTER:
            return self._compare(actual, target, True)
        if isinstance(target, (int, float)):
            return self._compare(actual, target, False)
        return actual == target

    def evaluate(self, condition: dict, player_data: dict) -> bool:
        if not condition:
            return True
        for key, target in condition.items():
            if not self._match_key(key, target, player_data.get(key)):
                return False
        return True

    def check_condition(
        self, aid: str, player_data: dict, character_id: str | None = None
    ) -> bool:
        achievement = self.achievements.get(aid)
        if achievement is None:
            return False
        player_data = player_data or {}
        satisfied = self.evaluate(achievement.condition, player_data)

        # 实时回退：条件不满足时完成状态立即失效（已领取奖励不受影响）
        self.completed[aid] = satisfied
        if achievement.condition:
            ratio = min(
                (self._condition_ratio(k, player_data.get(k), v)
                 for k, v in achievement.condition.items()),
                default=1.0,
            )
        else:
            ratio = 1.0 if satisfied else 0.0
        self.progress[aid] = int(ratio * 100)

        if satisfied:
            self.auto_claim(aid, character_id)
        return satisfied

    # ---------- 分类点数 ----------

    def _claimed_anywhere(self, aid: str) -> bool:
        if aid in self.claimed or aid in self.account_claimed:
            return True
        return any(aid in aids for aids in self.character_claimed.values())

    def get_category_points(self, category: str, character_id: str | None = None) -> int:
        if character_id is not None:
            return self.character_points.get(character_id, {}).get(category, 0)
        total = 0
        for aid, achievement in self.achievements.items():
            if achievement.category != category:
                continue
            # 完成中或已领取都计入：领取后即使条件失效也不扣回
            if self.completed.get(aid, False) or self._claimed_anywhere(aid):
                total += achievement.points
        return total

    def get_shop(self, category: str) -> Shop | None:
        return self.shops.get(category)

    def purchase(self, character_id: str, category: str, item_id: str) -> bool:
        shop = self.shops.get(category)
        item = shop.get_item(item_id) if shop else None
        if item is None:
            return False
        balance = self.get_category_points(category, character_id)
        if balance < item.cost:
            return False
        self.character_points.setdefault(
            character_id, {c: 0 for c in CATEGORIES}
        )[category] = balance - item.cost
        return True

    # ---------- 称号装备 ----------

    def equip_title(self, tid: str) -> bool:
        if tid not in self.titles:
            return False
        self.unequip_title()
        self.equipped_title = tid
        self.titles[tid].equipped = True
        return True

    def unequip_title(self, tid: str | None = None) -> bool:
        current = self.equipped_title
        if current is None:
            return False
        if tid is not None and current != tid:
            return False
        self.titles[current].equipped = False
        self.equipped_title = None
        return True

    def get_title_stats(self, tid: str) -> dict:
        title = self.titles.get(tid)
        if title is None:
            return {}
        if self.equipped_title != tid or not title.equipped:
            return {}
        return dict(title.stats)

    # ---------- 隐藏提示 ----------

    def describe_condition(self, aid: str) -> str:
        achievement = self.achievements.get(aid)
        if achievement is None:
            return ""
        if not achievement.condition:
            return achievement.name or "完成成就"
        parts = []
        for key, raw in achievement.condition.items():
            value = raw["value"] if isinstance(raw, dict) and "value" in raw else raw
            template = _CONDITION_LABELS.get(key)
            if template:
                parts.append(template.format(value=value))
            elif isinstance(value, str):
                parts.append(value)
            else:
                parts.append(f"{key}达到{value}")
        return "，".join(parts)

    def get_hint(self, aid: str) -> str:
        achievement = self.achievements.get(aid)
        if achievement is None:
            return ""
        if achievement.hidden and not self.completed.get(aid, False):
            return achievement.hint or _VAGUE_HINT
        return self.describe_condition(aid)

    # ---------- 自动领取 / 分区 ----------

    def _claim_key(self, aid: str, character_id: str | None) -> str:
        return f"{character_id}_{aid}" if character_id is not None else aid

    def is_claimed(self, aid: str, character_id: str | None = None) -> bool:
        if character_id is None:
            return self._claimed_anywhere(aid)
        if aid in self.character_claimed.get(character_id, set()):
            return True
        # 兼容 character_id_aid 形式的台账键
        return self._claim_key(aid, character_id) in self.claimed

    def auto_claim(self, aid: str, character_id: str | None = None) -> bool:
        achievement = self.achievements.get(aid)
        if achievement is None or not self.completed.get(aid, False):
            return False
        # 防刷：账号内任一角色已领取过该成就，不得重复领取
        if aid in self.account_claimed:
            return False
        key = self._claim_key(aid, character_id)
        if character_id is None:
            if key in self.claimed:
                return False
        elif aid in self.character_claimed.get(character_id, set()):
            return False

        if character_id is None:
            self.claimed.add(key)
        else:
            self.character_claimed.setdefault(character_id, set()).add(aid)
        self.account_claimed.add(aid)
        self.points[achievement.category] += achievement.points
        owner = character_id or DEFAULT_CHARACTER
        balances = self.character_points.setdefault(
            owner, {c: 0 for c in CATEGORIES}
        )
        balances[achievement.category] += achievement.points
        if achievement.title:
            self.titles.setdefault(
                achievement.title, Title(achievement.title, achievement.title)
            )
        return True

    def is_points_claimable(self, character_id: str | None = None) -> bool:
        for aid, done in self.completed.items():
            if not done:
                continue
            if character_id is None:
                pending = aid not in self.claimed
            else:
                claimed_by_char = (
                    aid in self.character_claimed.get(character_id, set())
                    or self._claim_key(aid, character_id) in self.claimed
                )
                pending = not claimed_by_char
            if pending and aid not in self.account_claimed:
                return True
        return False

    def get_claimable(self, character_id: str | None = None) -> list[str]:
        result = []
        for aid, done in self.completed.items():
            if character_id is None:
                pending = aid not in self.claimed
            else:
                claimed_by_char = (
                    aid in self.character_claimed.get(character_id, set())
                    or self._claim_key(aid, character_id) in self.claimed
                )
                pending = not claimed_by_char
            if done and pending and aid not in self.account_claimed:
                result.append(aid)
        return result

    def get_claimed_list(self, character_id: str | None = None) -> list[str]:
        result = []
        for aid in self.achievements:
            if self.is_claimed(aid, character_id):
                result.append(aid)
        return result

    def get_uncompleted(self) -> list[str]:
        return [
            aid
            for aid in self.achievements
            if not self.completed.get(aid, False)
            and not self._claimed_anywhere(aid)
        ]

    # ---------- 角色绑定 / 防刷 ----------

    def create_character(self, character_id: str) -> None:
        self.character_points.setdefault(
            character_id, {c: 0 for c in CATEGORIES}
        )

    def delete_character(self, character_id: str) -> int:
        balances = self.character_points.pop(character_id, {})
        cleared = sum(balances.values())
        self.character_claimed.pop(character_id, None)
        if self.equipped_title:
            title = self.titles.get(self.equipped_title)
            if title is not None:
                title.equipped = False
            self.equipped_title = None
        # account_claimed 故意保留：删号重建不能再领取同一成就
        return cleared
