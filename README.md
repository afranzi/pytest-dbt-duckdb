# pytest-dbt-duckdb 🦆✨

Fearless testing for dbt models, powered by DuckDB.

## "What is this?"

pytest-dbt-duckdb is an open-source testing framework that allows you to validate dbt models end-to-end, using DuckDB as
an in-memory execution engine. Designed for speed, portability, and CI/CD automation, it enables you to test dbt
transformations before deployment, ensuring trust in your data.

## 🎬 The Story: Why This Library Exists

> "Every data pipeline is a story. Every transformation, a chapter. But even the best tales can hide errors between the
> lines."

Modern analytics teams move fast—but in their race to ship, they often skip a crucial step: rigorous testing. A broken
transformation can mean misreported revenue, misleading product insights, or silent failures that creep into dashboards.

Here, in the shadows of SQL models and YAML configurations, we forge a guardian—a pytest plugin that ensures every dbt
model is battle-tested, validated, and ready before it touches production.

This is pytest-dbt-duckdb:
- ✅ Define test cases with simple YAML scenarios.
- ✅ Execute them in DuckDB, locally and instantly—no warehouse needed.
- ✅ Integrate with CI/CD pipelines, catching errors before deployment.
- ✅ Extend with custom DuckDB functions for specialized assertions.

Data must be tested, not trusted. Let’s test fearlessly.
