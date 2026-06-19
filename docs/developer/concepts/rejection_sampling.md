[<-- Back to Main Index](../../README.md)

# Rejection Sampling

Rejection Sampling is a technique used to enforce constraints during synthetic data generation without distorting the underlying statistical correlations learned by the model.

Unlike [Logical Rules](logical_rules.md) which use POST-processing "clipping" (which can [distort correlations](logical_rules.md#correlation-distortion)), Rejection Sampling operates by generating a record, checking it against a rule, and discarding it if it fails, repeating the process until a valid record is produced.

## Configuration

Rejection sampling must be configured globally in rules.yaml, then a rule may be set to opt-in:

```yaml
rejection_sampling:
	max_attempts: 5
	overgenerate_factor: 2.0

rules:
	- type: "numeric_threshold"
		table_target: "dataset_prueba_tecnica_v2"
		target_col: "age"
		threshold: 18
		operator: ">="
		rejection_sampling: true

	- type: "date_inequality"
		table_target: "person"
		target_col: "birth_datetime"
		constraint_operator: ">="
		constraint: "3/10/2002"
		rejection_sampling: true

```
Max attempts refers to the maximum number of rounds of rejection sampling that will be performed. If we still have not reached the desired number of rows after these rounds, then we simply return the result, noting that we have not reached the desired amount of rows. 

Max overgenerate factor allows us to speed up the process for complicated, often failing, rules. During each round of rejection sampling, we will prompt mostly to generate (remaining rows needed) * (overgenerate factor). For instance, if we set overgenerate factor to 5.0 and ask for 1000 rows, we will initially generate 5000 rows to filter. This can lead to returning more data then requested. We cannot simply cap the number of returned rows, as it the default in Mostly (and usually desired) that some tables generate more than the requested amount (ex. 1000 individual patients but many more measurements). Therefore, the user should be aware that setting a large value for the overgenerate factor can lead to increased computational costs and excess data.

Rules flagged with `rejection_sampling: true` are not applied in PRE or POST. They are only
evaluated during simulation, and failing rows are discarded.

## Behavior

- Rejection sampling is applied only to rules with the flag set.
- The rejection sampling rule SANITY CHECK is run. Rows that fail are removed.
- Deletions cascade to child tables using the metadata foreign keys to preserve referential integrity.
- Generation repeats until the requested `sample_size` is reached or the maximum number of attempts
	is exhausted.
- If the maximum attempts are reached early, the simulation returns partial results and records a
	warning in the simulation card and report.


[<-- Back to Main Index](../../README.md)
