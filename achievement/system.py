"""成就系统

修复内容:
1. track_achievement: 监听所有相关事件类型, 进度原子更新(线程安全)
2. check_condition: 支持计数/限时/无伤害/通用事件条件及 and/or 组合
3. unlock_achievement: 防重复解锁, 解锁通知玩家, 记录解锁历史
4. claim_reward: 支持金币/物品/称号/皮肤等多类型奖励, 防重复领取, 发放失败重试
5. get_achievement_list: 隐藏成就未解锁时不显示详情
"""
import threading
import time
from dataclasses import dataclass, field

REWARD_TYPES = ("gold", "item", "title", "skin")

# 成就条件类型 -> 触发进度的事件类型集合
_CONDITION_EVENTS = {
    "kill": {"kill"},
    "level_up": {"level_up"},
    "speed_kill": {"kill"},
    "no_damage_clear": {"damage", "clear"},
}


@dataclass
class Achievement:
    aid: str
    name: str
    condition: dict
    progress: int = 0
    unlocked: bool = False
    hidden: bool = False
    reward: dict = field(default_factory=dict)
    reward_claimed: bool = False


class AchievementSystem:
    def __init__(self, notifier=None, mail_sender=None, max_retries: int = 3):
        self.achievements: dict[str, Achievement] = {}
        self.unlocked_history: list = []
        self.claim_history: list = []
        self._events: dict[str, list] = {}
        self._lock = threading.RLock()
        self._notifier = notifier
        self._mail_sender = mail_sender
        self._max_retries = max_retries

    # ---- bug1: 事件监听 + 原子进度更新 ----

    def _relevant_events(self, condition: dict) -> set:
        ctype = condition.get("type", "count")
        if ctype in ("and", "or"):
            events = set()
            for sub in condition.get("conditions", []):
                events |= self._relevant_events(sub)
            return events
        if ctype == "count":
            return {condition.get("event", "kill")}
        return _CONDITION_EVENTS.get(ctype, {ctype})

    def track_achievement(self, aid: str, event: dict) -> None:
        with self._lock:
            ach = self.achievements.get(aid)
            if not ach or ach.unlocked:
                return
            etype = event.get("type")
            if etype not in self._relevant_events(ach.condition):
                return
            entry = dict(event)
            entry.setdefault("ts", time.time())
            self._events.setdefault(aid, []).append(entry)
            if etype != "damage":
                ach.progress += 1

    # ---- bug2: 复杂条件 + 组合条件 ----

    def check_condition(self, condition: dict, progress: int, events: list = None) -> bool:
        ctype = condition.get("type", "count")
        if ctype == "and":
            return all(self.check_condition(c, progress, events)
                       for c in condition.get("conditions", []))
        if ctype == "or":
            return any(self.check_condition(c, progress, events)
                       for c in condition.get("conditions", []))
        if ctype == "speed_kill":
            if events:
                kills = sorted(e.get("ts", 0) for e in events if e.get("type") == "kill")
                window = condition.get("time", 0)
                need = condition.get("count", 1)
                return any(kills[i + need - 1] - kills[i] <= window
                           for i in range(len(kills) - need + 1))
            return progress >= condition.get("count", 999)
        if ctype == "no_damage_clear":
            if events:
                cleared = any(e.get("type") == "clear" for e in events)
                damaged = any(e.get("type") == "damage" for e in events)
                return cleared and not damaged
            return progress >= condition.get("count", 1)
        # count / kill / level_up / 其他通用计数条件
        return progress >= condition.get("count", 999)

    # ---- bug3: 解锁防重复 + 通知 + 历史 ----

    def unlock_achievement(self, aid: str, player_id: str = None) -> bool:
        with self._lock:
            ach = self.achievements.get(aid)
            if not ach or ach.unlocked:
                return False
            ach.unlocked = True
            self.unlocked_history.append({
                "aid": aid,
                "player_id": player_id,
                "timestamp": time.time(),
            })
        self._notify(aid, player_id)
        return True

    def _notify(self, aid: str, player_id: str = None) -> None:
        if self._notifier:
            self._notifier({
                "type": "achievement_unlocked",
                "aid": aid,
                "player_id": player_id,
                "timestamp": time.time(),
            })

    # ---- bug4: 多类型奖励 + 防重复领取 + 失败重试 ----

    def claim_reward(self, aid: str, player_id: str = None) -> dict:
        with self._lock:
            ach = self.achievements.get(aid)
            if not ach or ach.reward_claimed:
                return {}
            reward = {k: v for k, v in ach.reward.items() if k in REWARD_TYPES}
            if not reward:
                ach.reward_claimed = True
                return {}
        if not self._deliver(reward, player_id):
            raise RuntimeError(f"reward delivery failed for achievement {aid}")
        with self._lock:
            ach.reward_claimed = True
            self.claim_history.append({
                "aid": aid,
                "player_id": player_id,
                "reward": reward,
                "timestamp": time.time(),
            })
        return reward

    def _deliver(self, reward: dict, player_id: str = None) -> bool:
        if self._mail_sender is None:
            return True
        for _ in range(self._max_retries):
            try:
                if self._mail_sender(reward, player_id):
                    return True
            except Exception:
                pass
        return False

    # ---- bug5: 隐藏成就未解锁不显示 ----

    def get_achievement_list(self) -> list:
        with self._lock:
            return [ach for ach in self.achievements.values()
                    if not ach.hidden or ach.unlocked]
