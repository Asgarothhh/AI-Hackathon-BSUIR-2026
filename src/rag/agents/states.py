import operator
from typing import Annotated, List, Literal, Optional, TypedDict

from pydantic import BaseModel, Field


class LegalChange(BaseModel):
    """"Описание конкретного изменения в тексте"""
    was_text: str = Field(description="Исходная формулировка (Старая редакция)")
    became_text: str = Field(description="Новая формулировка (Новая редакция)")
    change_type: Literal["structural", "semantic"] = Field(description="Тип изменения: структурное или смысловое")
    meaning_diff: str = Field(description="Краткое описание изменения юридического смысла (напр. 'право' стало 'обязанностью')")


class ComplianceRisk(BaseModel):
    """Результат проверки на соответствие вышестоящему законодательству"""
    risk_level: Literal["green", "yellow", "red"] = Field(description="Уровень риска: зеленый (ок), желтый (внимание), красный (противоречие)")
    violated_act: str = Field(description="Наименование НПА, которому может противоречить пункт (напр. 'Закон № 200-З')")
    article_ref: str = Field(description="Конкретная статья или пункт вышестоящего акта")
    comment: str = Field(description="Юридически корректный комментарий или рекомендация")
    portal_link: Optional[str] = Field(description="Гиперссылка на Национальный правовой интернет-портал")


class AnalyzedSection(BaseModel):
    """Полный результат анализа одной статьи или пункта документа"""
    section_id: str = Field(description="Номер статьи или пункта (напр. 'п. 3.1')")
    changes: List[LegalChange] = Field(description="Список найденных изменений в этой секции")
    risks: List[ComplianceRisk] = Field(description="Список выявленных рисков и противоречий")


class State(TypedDict):
    # Входные документы
    old_doc_text: str
    new_doc_text: str

    # Список задач (секций документа), которые определит оркестратор
    sections_to_analyze: List[AnalyzedSection]
    # Параллельно заполняемый список результатов от всех Воркеров
    completed_analysis: Annotated[List[AnalyzedSection], operator.add]

    # Итоговый путь к сгенерированному отчету или сам текст отчета
    final_report_metadata: dict


class WorkerState(TypedDict):
    # Конкретная секция, которую нужно проверить
    section: AnalyzedSection
    # Контекст: иерархия НПА, актуальная для данной проверки
    hierarchy_level: str
    # Поле для записи результата (отправляется обратно в глобальный State)
    completed_analysis: Annotated[List[AnalyzedSection], operator.add]


class Sections(BaseModel):
    """Список всех найденных разделов документа для анализа"""
    sections: List[Annotated[AnalyzedSection, "Разделы для проверки"]]


class MinimalSection(BaseModel):
    """Минимальный набор данных для того, чтобы нарезать документ на части"""
    section_id: str = Field(description="ID пункта (напр. 'п. 4.2')")
    old_text: str = Field(description="Текст из старой редакции")
    new_text: str = Field(description="Текст из новой редакции")


class OrchestratorPlan(BaseModel):
    """То, что вернет planner.with_structured_output(OrchestratorPlan)"""
    sections: List[MinimalSection]
