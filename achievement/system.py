"""成就系统

- 进度追踪: 监听所有事件类型, 锁保护下原子更新, 满足条件自动解锁
- 条件检查: 支持计数 / 限时计数 / 无伤害通关 / 组合(与、或)条件
- 解锁: 防重复, 通知玩家, 记录解锁历史
- 奖励: 支持金币/物品/称号/皮肤等多类型, 防重复领取, 发放失败重试
- 隐藏成就: 未解锁时不出现在列表中
"""
import time
import threading
from dataclasses import dataclass, field

REWARD_MAX_ATTEMPTS = 3


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


class MailSystem:
    """默认邮箱: 内存实现, 可通过 mailer 参数替换为真实邮件网关。"""

    def __init__(self):
        self.inbox: list = []

    def send(self, aid: str, reward: dict) -> None:
        self.inbox.append({"aid": aid, "reward": dict(reward)})


class AchievementSystem:
    def __init__(self, mailer=None, notifier=None):
        self.achievements: dict[str, Achievement] = {}
        self.unlocked_history: list = []
        self.notifications: list = []
        self.mailbox = mailer if mailer is not None else MailSystem()
        self._notifier = notifier
        self._lock = threading.RLock()
        self._event_log: dict[str, list] = {}
        self._damage_flags: dict[str, bool] = {}

    # ---------- 进度追踪 ----------

    def track_achievement(self, aid: str, event: dict) -> None:
        """监听所有类型的事件, 在锁保护下原子地更新进度。"""
        ach = self.achievements.get(aid)
        if ach is None:
            return
        event_type = event.get("type")
        with self._lock:
            if event_type == "damage":
                self._damage_flags[aid] = True
                return
            self._event_log.setdefault(aid, []).append(
                (time.monotonic(), event_type)
            )
            if ach.condition.get("type") == "no_damage_clear":
                ach.progress = (
                    1 if event_type == "clear"
                    and not self._damage_flags.get(aid) else 0
                )
            else:
                ach.progress = self._evaluate_progress(ach.condition, aid)
            if not ach.unlocked and self._condition_met(ach.condition, aid):
                self.unlock_achievement(aid)

    def _condition_met(self, condition: dict, aid: str) -> bool:
        """基于事件日志评估条件是否真正达成(供追踪时自动解锁使用)。"""
        cond_type = condition.get("type", "count")
        if cond_type == "composite":
            results = [
                self._condition_met(sub, aid)
                for sub in condition.get("conditions", [])
            ]
            op = condition.get("op", "and")
            return all(results) if op == "and" else any(results)
        if cond_type == "no_damage_clear":
            events = self._event_log.get(aid, [])
            return (
                any(etype == "clear" for _, etype in events)
                and not self._damage_flags.get(aid)
            )
        return self.check_condition(
            condition, self._evaluate_progress(condition, aid)
        )

    def _evaluate_progress(self, condition: dict, aid: str) -> int:
        cond_type = condition.get("type", "count")
        events = self._event_log.get(aid, [])
        if cond_type == "speed_kill":
            window = condition.get("time", 0)
            now = time.monotonic()
            return sum(1 for ts, _ in events if now - ts <= window)
        if cond_type == "composite":
            return sum(
                1 for sub in condition.get("conditions", [])
                if self.check_condition(sub, self._evaluate_progress(sub, aid))
            )
        return len(events)

    # ---------- 条件检查 ----------

    def check_condition(self, condition: dict, progress: int) -> bool:
        cond_type = condition.get("type", "count")
        if cond_type == "composite":
            results = [
                self.check_condition(sub, progress)
                for sub in condition.get("conditions", [])
            ]
            op = condition.get("op", "and")
            return all(results) if op == "and" else any(results)
        if cond_type == "no_damage_clear":
            return progress >= 1
        # count / speed_kill 等计数类条件
        return progress >= condition.get("count", 999)

    # ---------- 解锁 ----------

    def unlock_achievement(self, aid: str) -> bool:
        """解锁成就: 防重复, 通知玩家, 记录历史。重复解锁返回 False。"""
        with self._lock:
            ach = self.achievements.get(aid)
            if ach is None or ach.unlocked:
                return False
            ach.unlocked = True
            self.unlocked_history.append({"aid": aid, "unlocked_at": time.time()})
        self._notify(aid, ach.name)
        return True

    def _notify(self, aid: str, name: str) -> None:
        message = {"type": "achievement_unlocked", "aid": aid, "name": name}
        self.notifications.append(message)
        if self._notifier is not None:
            self._notifier(message)

    # ---------- 奖励 ----------

    def claim_reward(self, aid: str):
        """领取奖励: 支持多类型, 防重复, 发放失败重试, 成功才标记已领。"""
        with self._lock:
            ach = self.achievements.get(aid)
            if ach is None or ach.reward_claimed:
                return None
            reward = dict(ach.reward)
            if not reward:
                return None
            for _ in range(REWARD_MAX_ATTEMPTS):
                try:
                    self._deliver_reward(aid, reward)
                    break
                except Exception:
                    continue
            else:
                return None
            ach.reward_claimed = True
            return reward

    def _deliver_reward(self, aid: str, reward: dict) -> None:
        mailer = self.mailbox
        for method_name in ("send", "send_mail", "deliver"):
            method = getattr(mailer, method_name, None)
            if callable(method):
                method(aid, reward)
                return
        if callable(mailer):
            mailer(aid, reward)
            return
        raise RuntimeError("no usable mail delivery interface")

    # ---------- 列表 ----------

    def get_achievement_list(self) -> list:
        """成就列表: 未解锁的隐藏成就不显示。"""
        return [
            ach for ach in self.achievements.values()
            if not ach.hidden or ach.unlocked
        ]
