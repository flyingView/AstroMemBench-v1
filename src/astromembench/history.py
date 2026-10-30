"""Deliver past facts without replaying actions or generating new receipts."""


class HistoryFailure(RuntimeError):
    """Native model processing ended before all prescribed inputs were read."""


class HistoryLedger:
    def __init__(self, task):
        task.validate()
        self.events = task.history
        self.index = 0
        self.pending = None
        self.acknowledgments = []

    def begin(self):
        if self.pending is not None or self.index >= len(self.events):
            raise RuntimeError("No next history round is available")
        self.pending = self.events[self.index]
        return self.pending.public_input()

    def finish(self, *, processed, assistant_text=None, action_attempted=False):
        if self.pending is None:
            raise RuntimeError("No history round is pending")
        if not processed:
            raise HistoryFailure("Native model processing did not complete this history round")
        # Acknowledgment style is recorded, not converted into a task score.
        # The environment tool rejects attempts at this stage; no physics changes.
        self.acknowledgments.append({"round": self.index + 1, "text": assistant_text,
                                    "requested_ack": assistant_text == "收到",
                                    "environment_action_attempted": bool(action_attempted)})
        self.index += 1
        self.pending = None

    def check_boundary(self, task):
        if self.pending is not None or self.index != len(task.history):
            raise RuntimeError("All prescribed history rounds must finish before testing")
