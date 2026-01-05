"""Base strategy module"""
class BaseStrategy:
    def execute(self, data):
        return {"status": "success", "message": "Strategy executed"}
