"""成就点数与称号系统"""
from dataclasses import dataclass, field

@dataclass
class Achievement:
    aid: str
    name: str
    category: str  # pve/pvp/life/explore
    points: int
    condition: dict
    hidden: bool = False
    hint: str = ""

@dataclass
class Title:
    tid: str
    name: str
    stats: dict = field(default_factory=dict)
    equipped: bool = False

class AchievementSystem:
    def __init__(self):
        self.achievements: dict[str, Achievement] = {}
        self.completed: dict[str, bool] = {}
        self.points: dict[str, int] = {}  # category -> points
        self.titles: dict[str, Title] = {}
        self.claimed: set = set()

    def check_condition(self, aid: str, player_data: dict) -> bool:
        # 实时校验：条件不再满足时进度回退（已领取奖励不扣）
        if aid not in self.achievements:
            return False
        condition = self.achievements[aid].condition
        if not condition:
            return self.completed.get(aid, False)
        for key, required in condition.items():
            current = player_data.get(key)
            if current is None:
                return False
            if key == "rank":
                if current > required:
                    return False
            elif current < required:
                return False
        return True

    def get_category_points(self, category: str) -> int:
        # 按类别统计成就点数
        total = 0
        for aid, done in self.completed.items():
            if done and self.achievements[aid].category == category:
                total += self.achievements[aid].points
        return total

    def get_title_stats(self, tid: str) -> dict:
        # 称号只有装备时才生效
        if tid not in self.titles:
            return {}
        title = self.titles[tid]
        if not title.equipped:
            return {}
        return title.stats

    def equip_title(self, tid: str) -> bool:
        # 同时只能装备一个称号
        if tid not in self.titles:
            return False
        for title in self.titles.values():
            title.equipped = False
        self.titles[tid].equipped = True
        return True

    def get_hint(self, aid: str) -> str:
        # 隐藏成就给出模糊提示，完成后显示完整条件
        if aid not in self.achievements:
            return ""
        ach = self.achievements[aid]
        if ach.hidden and not self.completed.get(aid, False):
            return ach.hint or "在某处做某事"
        return str(ach.condition)

    def auto_claim(self, aid: str) -> bool:
        # 成就完成自动发放奖励并标记已领取
        if aid not in self.achievements:
            return False
        if not self.completed.get(aid, False):
            return False
        if aid in self.claimed:
            return False
        self.claimed.add(aid)
        return True

    def is_points_claimable(self, character_id: str) -> bool:
        # 成就点数与角色绑定，防重复获取/防刷
        prefix = f"{character_id}_"
        for key in self.claimed:
            if isinstance(key, str) and key.startswith(prefix):
                return False
        return True
