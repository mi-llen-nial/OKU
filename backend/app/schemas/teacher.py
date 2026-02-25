from pydantic import BaseModel


class GroupStudentMetric(BaseModel):
    student_id: int
    student_name: str
    tests_count: int
    avg_percent: float
    last_percent: float | None


class GroupTrendPoint(BaseModel):
    date: str
    avg_percent: float


class GroupAnalyticsResponse(BaseModel):
    group_id: int
    group_name: str
    students: list[GroupStudentMetric]
    group_avg_percent: float
    trend: list[GroupTrendPoint]


class WeakTopicItem(BaseModel):
    topic: str
    count: int


class GroupWeakTopicsResponse(BaseModel):
    group_id: int
    group_name: str
    weak_topics: list[WeakTopicItem]
