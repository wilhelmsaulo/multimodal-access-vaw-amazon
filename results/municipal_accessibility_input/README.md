# Municipal accessibility input

Status: **accessibility interval table prepared; structural/statistical audit not started**.

This directory converts the long E2SFCA coverage-sensitivity output into one row for each
of the 144 Pará municipalities. It retains 48 accessibility features: lower and upper
sensitivity endpoints for four service types under six threshold/decay specifications.
Female population and the routing-coverage fraction are retained as provenance and
coverage controls.

The table does not select a preferred E2SFCA point estimate, does not contain a
sociodemographic block, and is not authorized as a direct MCDM or SOM input. Its purpose
is to provide the accessibility component of the future municipal analytical table while
preserving routing-coverage uncertainty.

Before the next gate, the sociodemographic and institutional blocks must be explicitly
selected and versioned. The following stage will then audit missingness, temporal
compatibility, correlation, redundancy, VIF and, only if justified, PCA. That audit has
not been initiated by this materialization step.
