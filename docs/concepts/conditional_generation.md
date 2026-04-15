[<-- Back to Main Index](../../README.md)

# Conditional Generation

Conditional Generation allows you to synthesize specific columns of data while "anchoring" or conditioning the model generation on a provided data subset (the "seed"). 

## What it allows
Instead of generating an entirely new dataset from scratch, you can provide an existing DataFrame with specific pre-filled features (e.g., demographics) and instruct the engine to probabilistically generate the remaining features (e.g., diagnoses, medications) *conditioned* on the specific attributes of your provided seed.

## How it works
Under the hood, the TabularARGN model processes data sequentially by column. During conditional generation, the variables provided in the seed DataFrame are fed into the model as ground truth context. The model then executes its auto-regressive sequential generation exclusively for the missing columns, effectively predicting probability distributions that align with the provided seed attributes.

## How to use it
In the context of the Mostly AI SDK and our pipeline, conditional generation is typically invoked by passing a `seed` DataFrame to the generation/simulation workflow. The engine will respect the columns present in the seed and generate the complementary features.

## Native "Flexible Generation" vs. Custom Constraints

A common point of confusion is how to enforce **bounds** (e.g., `age > 18`) during conditional generation. 

### 1. Native Flexible Generation (Conditional)
Native "Flexible Generation" in MOSTLY AI (via the `seed` DataFrame) operates on **point values**.
- **What it does**: It "anchors" a specific value (e.g., `age = 25`) or a specific category.
- **What it CANNOT do**: It does **not** accept range operators or inequalities (like `> 18`) inside the seed DataFrame.
- **The Result**: If you seed `age = 25`, every record generated from that seed row will have *exactly* age 25. You lose diversity for that specific column, or you would need to generate the distribution of the column manually and set is as the list of values in the seed.

#### A Trick to get diversity within a bound natively
If you want to generate **diverse** values within a bound (e.g., "any age above 18") using only native features, you can try:
1. **Training Phase**: Ensure your dataset includes a categorical column e.g., `is_adult` (with values `True`/`False` based on the age column).
2. **Generation Phase**: In your seed DataFrame, set `is_adult = True`.
3. **Outcome**: The AI will generate diverse ages that statistically correspond to the "True" category, effectively respecting the bound while maintaining diversity.

### 2. Custom Logical Rules (Deterministic Bounds)
When statistical correlation is not enough and you need a **mathematical guarantee**, use our [Logical Rules](logical_rules.md) system (e.g., `NumericInequalityRule`).
- **What it does**: It transforms the data before training (calculating the difference relative to the bound) and reconstructs it after simulation.
- **Use Case**: When you must guarantee zero violations (e.g., ensuring no "infant" has a "driving license" or no "discharge date" is before "admission").
- **Difference**: Unlike native seeding, this handles the math for you and allows the model to generate diverse values that are *always* clipped or reconstructed to satisfy the bound.
- **🚨 Critical Limitation (Correlation Distortion)**: Forcing bounds that significantly contradict the training data via rules (e.g., forcing `age > 18` on a dataset with many children) will "break" correlations and create unnatural value spikes. See the detailed analysis in [Correlation Distortion in Logical Rules](logical_rules.md#correlation-distortion).

[<-- Back to Main Index](../../README.md)
