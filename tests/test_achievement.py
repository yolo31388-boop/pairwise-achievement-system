"""成就系统 - 红态测试"""
import pytest, sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from achievement.system import AchievementSystem, Achievement

class TestEventTracking:
    def test_all_events_tracked(self):
        asys = AchievementSystem()
        asys.achievements["a1"] = Achievement("a1", "test", {"type":"level_up","count":1})
        asys.track_achievement("a1", {"type": "level_up"})
        assert asys.achievements["a1"].progress == 1

class TestComplexCondition:
    def test_time_condition_supported(self):
        asys = AchievementSystem()
        cond = {"type": "speed_kill", "time": 10, "count": 5}
        assert asys.check_condition(cond, 5) == True

class TestNoDuplicateUnlock:
    def test_unlock_not_duplicated(self):
        asys = AchievementSystem()
        asys.achievements["a1"] = Achievement("a1", "test", {})
        asys.unlock_achievement("a1")
        asys.unlock_achievement("a1")
        assert len(asys.unlocked_history) == 1

class TestItemReward:
    def test_item_reward_claimable(self):
        asys = AchievementSystem()
        asys.achievements["a1"] = Achievement("a1", "test", {}, reward={"item": "badge"})
        reward = asys.claim_reward("a1")
        assert "item" in reward

class TestHiddenAchievement:
    def test_hidden_not_shown_when_locked(self):
        asys = AchievementSystem()
        asys.achievements["a1"] = Achievement("a1", "secret", {}, hidden=True)
        result = asys.get_achievement_list()
        assert len(result) == 0
