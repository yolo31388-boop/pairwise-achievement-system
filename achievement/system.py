"""成就点数与称号系统 - 含6个bug"""
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
        # bug1: 只增不减
        if aid not in self.achievements:
            return False
        return self.completed.get(aid, False)

    def get_category_points(self, category: str) -> int:
        # bug2: 不分类
        total = 0
        for aid, done in self.completed.items():
            if done:
                total += self.achievements[aid].points
        return total

    def get_title_stats(self, tid: str) -> dict:
        # bug3: 不装备也生效
        if tid not in self.titles:
            return {}
        return self.titles[tid].stats

    def get_hint(self, aid: str) -> str:
        # bug4: 隐藏成就无提示
        if aid not in self.achievements:
            return ""
        return self.achievements[aid].hint

    def auto_claim(self, aid: str) -> bool:
        # bug5: 不自动领取
        return False

    def is_points_claimable(self, character_id: str) -> bool:
        # bug6: 可重复获取
        return True
