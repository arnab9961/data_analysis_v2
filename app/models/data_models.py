class DataModel:
    def __init__(self, id: int, name: str, description: str):
        self.id = id
        self.name = name
        self.description = description

class AnalysisRequest:
    def __init__(self, data: list, analysis_type: str):
        self.data = data
        self.analysis_type = analysis_type

class AnalysisResult:
    def __init__(self, request_id: int, result: dict):
        self.request_id = request_id
        self.result = result