# :material-duck: PyTest dbt Duckdb

Fearless testing for dbt models, powered by DuckDB :simple-duckdb:.

!!! info "What is this?"
    **pytest-dbt-duckdb** is an open-source testing framework that allows you to validate dbt models end-to-end, using DuckDB as
    an in-memory execution engine. Designed for speed, portability, and CI/CD automation, it enables you to test dbt
    transformations before deployment, ensuring trust in your data.

## :octicons-zoom-in-24: Why This Exists

!!! danger "Assumptions are dangerous."
    An untested model is a ticking time bomb—silent, unseen, but waiting to fail at the worst possible moment.
    This library ensures your transformations, dependencies, and outputs are battle-tested before deployment.

## :octicons-light-bulb-24: Data must be tested, not trusted.

Modern analytics teams **move fast**—but in their race to ship, they often **skip a crucial step**: rigorous testing.
A broken transformation can mean misreported revenue, misleading product insights, or silent failures that creep into dashboards.

!!! tip ""
    "Each dbt model untested is a story unfinished."

Here, in the shadows of SQL models and YAML configurations, we forge a guardian—a pytest plugin
that ensures every dbt model is **battle-tested**, **validated**, and **ready** before it touches production.

With DuckDB as the testing engine, you can:

- [x] **Define** test cases with simple YAML scenarios.
- [x] **Execute** them in DuckDB, locally and instantly—no warehouse needed.
- [x] **Integrate** with **CI/CD pipelines**, catching errors before deployment.
- [x] **Extend** with **custom DuckDB functions** for specialized assertions.

Data must be tested, not trusted. Let’s test fearlessly.

<figure markdown="span">
  ![Image title](images/dbt-flow.jpg)
  <figcaption>DBT E2E Test Flow</figcaption>
</figure>

---

## :octicons-rocket-24: Who is this for?

!!! tip ""
    Whether you are a **craftsman of data** or a **guardian of analytics**, this library is **your lantern in the dark,
    guiding you toward precision and reliability**.

- :octicons-pin-24: **Data Engineers** → Validate dbt models before they reach production.
- :octicons-pin-24: **Analytics Engineers** → Ensure clean, tested data in dashboards.
- :octicons-pin-24: **CI/CD Developers** → Automate SQL testing in pull requests.

---

## :octicons-link-24: Key Features

| Feature                                        | Description                                                      |
|:-----------------------------------------------|:-----------------------------------------------------------------|
| :material-check-decagram: **Fast Testing**     | Runs entirely in DuckDB—no warehouse costs.                      |
| :material-hammer-wrench:️ **YAML-Based Tests**     | Define test scenarios using declarative YAML.                    |
| :material-refresh-circle: **CI/CD Ready**          | Seamless integration with GitHub Actions, Jenkins, GitLab CI/CD. |
| :material-power-plug-outline: **Custom Functions** | Extend with user-defined DuckDB functions.                       |
| :material-test-tube: **Snapshot Testing**          | Compare actual vs. expected outputs with precision.              |


---

## :octicons-git-commit-24: How It Works

:octicons-arrow-right-24: See the [Usage Section](usage.md)
