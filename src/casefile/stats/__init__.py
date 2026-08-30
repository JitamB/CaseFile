"""The statistics library — Track A, §27.

Every quantitative claim in a case is produced here or in SQL. Nothing in this
package knows what a hypothesis is: these are functions over numbers, and the
engine decides what they mean. That separation is what lets §35.1 check each one
against a hand-computed value rather than against the pipeline's own opinion.

Two rules hold across the package:

* **A test that cannot be run returns a verdict saying so**, never a number that
  looks like an answer. Spearman below n = 5 is the load-bearing case (§15 S5).
* **No function reads a contract, a case or the database.** Callers pass numbers
  in and get numbers out, so a failure is always reproducible from the test.
"""
