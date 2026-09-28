"""學生姓名與地區的本地比對（見功能規格 1.3）。

刻意完全不呼叫 LLM——學生名單不能傳給 LLM（減少個資外流），比對邏輯
也比對名字這種事更適合用確定性規則做，不需要動用語言模型。
"""
import difflib

from sqlalchemy.orm import Session

from app import models
from pydantic import BaseModel, Field

# 模糊比對的相似度門檻（difflib.SequenceMatcher.ratio()，0~1）。刻意用
# stdlib 的 difflib、不另外加 rapidfuzz 這個相依套件——量不大，精準度
# 目前夠用；如果之後模糊比對常常抓不到人，再考慮換掉。
# 中文姓名通常 2~4 個字，差一個字（最常見的打字/同音字誤差）算出來的
# ratio 大約落在 0.6~0.7 之間（例如「王小明」對「王曉明」是 0.667），
# 門檻設太高（例如 0.75）反而會漏掉這種最常見的情況，所以設 0.6。
FUZZY_MATCH_THRESHOLD = 0.6
# 模糊比對最多回傳幾個候選人供人工挑選
FUZZY_MATCH_MAX_CANDIDATES = 5


class StudentMatchResult(BaseModel):
    matched_student_id: int | None = None
    match_type: str | None = None  # "exact" | "alias" | None（模糊比對一律不自動選，見下）
    candidates: list[int] = Field(default_factory=list)  # 需要人工確認時的候選學生 id
    needs_review: bool = True


class AreaMatchResult(BaseModel):
    matched_venue_ids: list[int] = Field(default_factory=list)
    needs_review: bool = True


def match_student(db: Session, name: str) -> StudentMatchResult:
    """完全相同 > 別名 > 模糊比對。模糊比對不管找到幾個都一律標記需要
    人工確認、不自動選——模糊比對本質上就是不確定，不該自動變成正式
    資料（見規格設計原則 2：錯的資料不能往下流）。"""
    exact = db.query(models.Student).filter(models.Student.name == name).all()
    if len(exact) == 1:
        return StudentMatchResult(
            matched_student_id=exact[0].id, match_type="exact", needs_review=False
        )
    if len(exact) > 1:
        return StudentMatchResult(candidates=[s.id for s in exact])

    alias_rows = (
        db.query(models.StudentAlias).filter(models.StudentAlias.alias == name).all()
    )
    alias_student_ids = sorted({row.student_id for row in alias_rows})
    if len(alias_student_ids) == 1:
        return StudentMatchResult(
            matched_student_id=alias_student_ids[0], match_type="alias", needs_review=False
        )
    if len(alias_student_ids) > 1:
        return StudentMatchResult(candidates=alias_student_ids)

    all_students = db.query(models.Student).all()
    all_aliases = db.query(models.StudentAlias).all()
    scores: dict[int, float] = {}
    for student in all_students:
        scores[student.id] = difflib.SequenceMatcher(None, name, student.name).ratio()
    for alias_row in all_aliases:
        ratio = difflib.SequenceMatcher(None, name, alias_row.alias).ratio()
        if ratio > scores.get(alias_row.student_id, 0):
            scores[alias_row.student_id] = ratio

    candidates = sorted(
        (sid for sid, score in scores.items() if score >= FUZZY_MATCH_THRESHOLD),
        key=lambda sid: scores[sid],
        reverse=True,
    )[:FUZZY_MATCH_MAX_CANDIDATES]
    return StudentMatchResult(candidates=candidates)


def match_area(db: Session, area: str) -> AreaMatchResult:
    """地區字串完全比對 VenueArea 表，找不到就標記需要人工確認。"""
    rows = db.query(models.VenueArea).filter(models.VenueArea.area == area).all()
    venue_ids = sorted({row.venue_id for row in rows})
    return AreaMatchResult(matched_venue_ids=venue_ids, needs_review=len(venue_ids) == 0)
