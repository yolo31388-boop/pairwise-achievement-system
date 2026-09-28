"""成就点数与称号系统 - 红态测试"""
import pytest, sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from achievement.system import AchievementSystem, Achievement, Title

class TestConditionRealtime:
    def test_lost_condition_revokes(self):
        asys = AchievementSystem()
        asys.achievements["top100"] = Achievement("top100", "排名前100", "pvp", 100, {"rank": 100})
        asys.completed["top100"] = True
        # 玩家掉出前100，成就应该失效
        assert asys.check_condition("top100", {"rank": 200}) == False  # bug1: 还是True

class TestCategoryPoints:
    def test_points_separated_by_category(self):
        asys = AchievementSystem()
        asys.achievements["pve1"] = Achievement("pve1", "pve", "pve", 50, {})
        asys.achievements["pvp1"] = Achievement("pvp1", "pvp", "pvp", 50, {})
        asys.completed = {"pve1": True, "pvp1": True}
        assert asys.get_category_points("pve") == 50  # bug2: 返回100
        assert asys.get_category_points("pvp") == 50

class TestTitleRequiresEquip:
    def test_unequipped_title_no_stats(self):
        asys = AchievementSystem()
        asys.titles["t1"] = Title("t1", "Conqueror", stats={"atk": 100}, equipped=False)
        stats = asys.get_title_stats("t1")
        assert stats == {}  # bug3: 不装备也有100atk

class TestHiddenHint:
    def test_hidden_achievement_has_vague_hint(self):
        asys = AchievementSystem()
        asys.achievements["secret"] = Achievement("secret", "???", "explore", 200, {}, hidden=True, hint="在某处做某事")
        hint = asys.get_hint("secret")
        assert hint != ""  # bug4: 空

class TestAutoClaim:
    def test_completed_achievement_auto_claimed(self):
        asys = AchievementSystem()
        asys.achievements["a1"] = Achievement("a1", "a1", "pve", 10, {})
        asys.completed["a1"] = True
        result = asys.auto_claim("a1")
        assert result == True  # bug5: False
        assert "a1" in asys.claimed

class TestPointsBoundToChar:
    def test_points_cannot_be_claimed_twice(self):
        asys = AchievementSystem()
        asys.achievements["a1"] = Achievement("a1", "a1", "pve", 10, {})
        asys.completed["a1"] = True
        asys.claimed.add("char1_a1")
        assert asys.is_points_claimable("char1") == False  # bug6: True
