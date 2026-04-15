[<-- Back to Main Index](../../README.md)

# Rejection Sampling (Upcoming Feature)

Rejection Sampling is a technique used to enforce constraints during synthetic data generation without distorting the underlying statistical correlations learned by the model. 

Unlike [Logical Rules](logical_rules.md) which use POST-processing "clipping" (which can [distort correlations](logical_rules.md#correlation-distortion)), Rejection Sampling operates by generating a record, checking it against a rule, and discarding it if it fails, repeating the process until a valid record is produced.


[<-- Back to Main Index](../../README.md)
