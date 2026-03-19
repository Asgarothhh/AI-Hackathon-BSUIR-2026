from typing import List, Dict
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.output_parsers import JsonOutputParser
from pydantic import BaseModel, Field
from src.rag.agents.llm_call import get_llm

class DocumentAnalysis(BaseModel):
    summary: str = Field(description='Краткое содержание документа')
    definitions: List[Dict[str, str]] = Field(description='Список ключевых терминов и их определений. Формат: {\"term\": \"...\", \"definition\": \"...\"}')

class DocumentAgent:
    def __init__(self):
        self.llm = get_llm()
        self.parser = JsonOutputParser(pydantic_object=DocumentAnalysis)

    def process_document(self, content: str) -> Dict:
        """
        Обрабатывает текст документа: извлекает summary и ключевые определения.
        """
        system_prompt = (
            'Ты — экспертный аналитик документов. Твоя задача — проанализировать предоставленный текст, '
            'составить краткое резюме (summary) и выделить все важные термины с их определениями. '
            'Ответ должен быть строго в формате JSON.'
        )
        
        human_prompt = f'Проанализируй следующий текст:\n\n{content}\n\n{self.parser.get_format_instructions()}'
        
        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=human_prompt)
        ]
        
        try:
            response = self.llm.invoke(messages)
            return self.parser.parse(response.content)
        except Exception as e:
            return {'error': str(e), 'summary': '', 'definitions': []}

    def batch_process(self, documents: List[str]) -> List[Dict]:
        """Пакетная обработка списка текстов."""
        results = []
        for doc in documents:
            results.append(self.process_document(doc))
        return results
