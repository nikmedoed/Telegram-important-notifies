import unittest

from service.search_engine import find_phrase, find_queries, parse_query_phrase


class SearchEngineTests(unittest.TestCase):
    def setUp(self) -> None:
        # Realistic vacancy snippets (trimmed) grouped by role.
        self.data = {
            "python_backend": """Python разработчик backend
Python 3.11 aiohttp FastAPI sanic PostgreSQL Redis Kafka RabbitMQ Docker GitLab CI CD highload.""",
            "java_senior": """Java Developer Senior
Java 17 Spring Boot Oracle PostgreSQL Kafka RabbitMQ Docker Kubernetes Rest API EhCache.""",
            "vue_senior": """Senior Vue.js Developer
Vue 3 SPA архитектура TypeScript Git высоконагруженные приложения.""",
            "flutter_middle": """Middle Flutter Developer
Flutter Dart Bloc Clean Architecture REST API адаптивные интерфейсы анимации.""",
            "devops_middle": """DevOps Middle
Terraform Ansible Linux Nginx Python Bash Docker Kubernetes Prometheus Grafana CI CD.""",
            "unity_game": """Unity Game Developer
Unity URP C# DOTween Addressables mobile games iOS Android оптимизация CPU GPU RAM.""",
            "ba_fullstack": """Fullstack-аналитик — Senior
Бизнес-анализ, BPMN, UML, BRD, FRD, API, коммуникация с бизнесом.""",
            "qa_fullstack": """QA Fullstack Python
Ручное 70% / авто 30% на Python, тестирование backend, Postman, SQL, GitLab, микросервисы.""",
            "product_manager": """Product Manager B2C
A/B тесты, метрики конверсии, GA4/Amplitude, User Stories, приоритизация backlog.""",
            "data_analyst": """Data аналитик Senior
SQL, Python, Spark, Hadoop, BI, MPP, визуализация данных, Tech Data Lake.""",
            "destination_specialist": """Destination Specialist travel sales
Plan custom tours, English communication, CRM, phone/email, commission-based.""",
            "java_teamlead": """Java Team Lead финтех
Java/Kotlin 4+ лет, PostgreSQL, высоконагруженные приложения, Spring, Hibernate, Docker, Kubernetes.""",
            "flutter_junior": """Flutter-разработчик junior/middle
Dart, Flutter, жесты, интерактивная карта, REST API, частичная занятость.""",
            "python_resume": """Python Backend Developer (FastAPI + AI/ML)
FastAPI, Celery, REST/gRPC, PostgreSQL, Redis, Docker, asyncio, WebSocket, RabbitMQ.""",
            "sales_remote": """Destination specialist (sales)
English sales, CRM, remote, commission, no cold calls.""",
        }

    def text(self, key: str) -> str:
        return self.data[key]

    # --- Positive hits -------------------------------------------------
    def test_python_backend_hit(self):
        res = find_queries(["python backend fastapi kafka docker"], self.text("python_backend"))
        self.assertIn("python backend fastapi kafka docker", res)
        self.assertGreaterEqual(res["python backend fastapi kafka docker"], 55.0)

    def test_java_senior_hit(self):
        res = find_queries(["senior java spring boot kafka kubernetes"], self.text("java_senior"))
        self.assertIn("senior java spring boot kafka kubernetes", res)

    def test_vue_senior_hit(self):
        score = find_phrase("senior vue 3 spa typescript", self.text("vue_senior"))
        self.assertGreaterEqual(score, 60.0)

    def test_flutter_middle_hit(self):
        res = find_queries(["flutter dart bloc clean architecture"], self.text("flutter_middle"))
        self.assertIn("flutter dart bloc clean architecture", res)

    def test_devops_hit(self):
        score = find_phrase("devops terraform ansible kubernetes", self.text("devops_middle"))
        self.assertGreaterEqual(score, 60.0)

    def test_unity_hit(self):
        score = find_phrase("unity c# mobile games addressables", self.text("unity_game"))
        self.assertGreaterEqual(score, 60.0)

    def test_ba_hit(self):
        res = find_queries(["бизнес аналитик bpmn uml api brd frd"], self.text("ba_fullstack"))
        self.assertIn("бизнес аналитик bpmn uml api brd frd", res)

    def test_qa_hit(self):
        score = find_phrase("qa python backend postman sql микросервисы", self.text("qa_fullstack"))
        self.assertGreaterEqual(score, 70.0)

    def test_product_manager_hit(self):
        res = find_queries(["product manager b2c ab тесты ga4 amplitude"], self.text("product_manager"))
        self.assertIn("product manager b2c ab тесты ga4 amplitude", res)

    def test_data_analyst_hit(self):
        score = find_phrase("data analyst sql python spark hadoop bi", self.text("data_analyst"))
        self.assertGreaterEqual(score, 70.0)

    # --- Negatives / disambiguation -----------------------------------
    def test_python_query_not_matching_java(self):
        res = find_queries(["python backend fastapi"], self.text("java_senior"))
        self.assertNotIn("python backend fastapi", res)

    def test_devops_query_not_matching_sales(self):
        res = find_queries(["devops kubernetes terraform ansible"], self.text("destination_specialist"))
        self.assertFalse(res)

    # --- Required token handling --------------------------------------
    def test_required_token_present(self):
        phrase = "+fastapi python backend"
        tokens, clauses = parse_query_phrase(phrase)
        clause = clauses[0]
        score = find_phrase(
            phrase,
            self.text("python_resume"),
            query_tokens=clause.tokens,
            required_tokens=clause.required,
        )
        self.assertGreaterEqual(score, 55.0)

    def test_required_token_missing(self):
        phrase = "+fastapi python backend"
        tokens, clauses = parse_query_phrase(phrase)
        clause = clauses[0]
        score = find_phrase(
            phrase,
            self.text("qa_fullstack"),  # есть Python, нет FastAPI
            query_tokens=clause.tokens,
            required_tokens=clause.required,
        )
        self.assertLess(score, 5.0)

    # --- Multi-clause / multiple matches ------------------------------
    def test_multi_clause_query(self):
        queries = ["python backend, kafka rabbitmq"]
        res = find_queries(queries, self.text("python_backend"))
        self.assertIn("python backend, kafka rabbitmq", res)

    def test_multiple_queries_only_relevant_returned(self):
        queries = [
            "flutter developer dart",
            "java team lead spring",
            "sales manager english crm",
        ]
        res = find_queries(queries, self.text("java_teamlead"))
        self.assertIn("java team lead spring", res)
        self.assertNotIn("flutter developer dart", res)
        self.assertNotIn("sales manager english crm", res)


if __name__ == "__main__":
    unittest.main()
