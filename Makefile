# §41.3 — the commands every verification in §44 refers to.
#
# `make check` is the contract with CI: it runs exactly what ci.yml runs, in the
# same order. If those two ever disagree, fixing the divergence outranks every
# other task in the project.

.PHONY: setup data corpus demo test check gate0 gate1 gate2 gate3 gate4 gate5 gate6

setup:
	pip install -e ".[dev]"

# Not yet implemented. These fail loudly rather than succeeding vacuously — a
# target that prints nothing and exits 0 reads as "it worked".
data:
	@echo "make data arrives at ladder step 0.7 — src/casefile/data/generator.py" >&2; exit 1

corpus:
	@echo "make corpus arrives at ladder step 1.5 — data/corpus/" >&2; exit 1

demo:
	@echo "make demo arrives at ladder step 3.1 — src/casefile/orchestrator.py" >&2; exit 1

test:
	pytest -q

check:
	ruff check src tests
	mypy src
	pytest -q

gate0 gate1 gate2 gate3 gate4 gate5 gate6:
	pytest -m $@ -q
