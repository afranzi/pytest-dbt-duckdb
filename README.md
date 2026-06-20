# PyTest dbt Duckdb 🦆

Fearless testing for dbt models, powered by DuckDB.

## What is this?
**pytest-dbt-duckdb** is an open-source testing framework that allows you to validate dbt models end-to-end, using DuckDB as
an in-memory execution engine. Designed for speed, portability, and CI/CD automation, it enables you to test dbt
transformations before deployment, ensuring trust in your data.

## 🩺 Why This Exists

"Assumptions are dangerous."
An untested model is a ticking time bomb—silent, unseen, but waiting to fail at the worst possible moment.
This library ensures your transformations, dependencies, and outputs are battle-tested before deployment.

---

## 💡 Data must be tested, not trusted.

Modern analytics teams **move fast**—but in their race to ship, they often **skip a crucial step**: rigorous testing.
A broken transformation can mean misreported revenue, misleading product insights, or silent failures that creep into dashboards.

> "Each dbt model untested is a story unfinished."

Here, in the shadows of SQL models and YAML configurations, we forge a guardian—a pytest plugin
that ensures every dbt model is **battle-tested**, **validated**, and **ready** before it touches production.

With DuckDB as the testing engine, you can:

- [x] **Define** test cases with simple YAML scenarios.
- [x] **Execute** them in DuckDB, locally and instantly—no warehouse needed.
- [x] **Integrate** with **CI/CD pipelines**, catching errors before deployment.
- [x] **Extend** with **custom DuckDB functions** for specialized assertions.

> Data must be tested, not trusted. Let’s test fearlessly.

![Image title](docs/images/dbt-flow.jpg)

---

## 🚀 Who is this for?


> Whether you are a **craftsman of data** or a **guardian of analytics**, this library is **your lantern in the dark,
guiding you toward precision and reliability**.

- [x] **Data Engineers** → Validate dbt models before they reach production.
- [x] **Analytics Engineers** → Ensure clean, tested data in dashboards.
- [x] **CI/CD Developers** → Automate SQL testing in pull requests.

---

## 🎯 Key Features

| Feature                  | Description                                                      |
|:-------------------------|:-----------------------------------------------------------------|
| ✅ **Fast Testing**       | Runs entirely in DuckDB—no warehouse costs.                      |
| 🛠️ **YAML-Based Tests** | Define test scenarios using declarative YAML.                    |
| ♻️ **CI/CD Ready**       | Seamless integration with GitHub Actions, Jenkins, GitLab CI/CD. |
| 🔌 **Custom Functions**  | Extend with user-defined DuckDB functions.                       |
| 🧪 **Snapshot Testing**  | Compare actual vs. expected outputs with precision.              |
| 🏷️ **Extra dbt Args**   | Pass arbitrary dbt CLI flags (e.g. microbatch date windows) to both `dbt seed` and `dbt build`, per scenario. |

---

## How It Works

➡️ See the [Usage Section](https://afranzi.github.io/pytest-dbt-duckdb/usage/)
