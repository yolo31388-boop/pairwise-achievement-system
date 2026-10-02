"""成就系统 - 含5个bug"""
from dataclasses import dataclass, field

@dataclass
class Achievement:
    aid: str
    name: str
    condition: dict
    progress: int = 0
    unlocked: bool = False
    hidden: bool = False
    reward: dict = field(default_factory=dict)

class AchievementSystem:
    def __init__(self):
        self.achievements: dict[str, Achievement] = {}
        self.unlocked_history: list = []  # bug3: 不记录

    def track_achievement(self, aid: str, event: dict) -> None:
        # bug1: 只监听特定事件
        if event.get("type") == "kill":
            ach = self.achievements.get(aid)
            if ach:
                ach.progress += 1

    def check_condition(self, condition: dict, progress: int) -> bool:
        # bug2: 只支持计数
        return progress >= condition.get("count", 999)

    def unlock_achievement(self, aid: str) -> bool:
        # bug3: 不防重复，不通知
        ach = self.achievements.get(aid)
        if ach:
            ach.unlocked = True
        return True

    def claim_reward(self, aid: str) -> dict:
        # bug4: 只支持金币，不防重复
        ach = self.achievements.get(aid)
        if ach:
            return {"gold": ach.reward.get("gold", 0)}
        return {}

    def get_achievement_list(self) -> list:
        # bug5: 隐藏成就直接显示
        return list(self.achievements.values())
