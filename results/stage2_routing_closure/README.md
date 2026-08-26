# Stage 2 routing closure

The definitive multimodal temporal graph and reference origin-destination construction stage was closed on 2026-08-26 after a successful coherence audit.

## Frozen evidence

- Closure workflow run: [32991298479](https://github.com/wilhelmsaulo/multimodal-access-vaw-amazon/actions/runs/32991298479)
- Closure artifact: `pa-stage2-routing-closure` (artifact ID `9614703180`)
- Closure artifact SHA-256: `16ce805fff20084d5a70eed58eb8fc445d742536f15f8b9734c9d5ca5d99372e`
- Frozen OD run: `32951714732`
- Frozen OD SHA-256: `faa831600003291544277c6fae4bbd9ee4fc71ec3ae0d8b167c040b9f65121e2`

## Audited counts

- 12,673 routing-ready primary origins
- 225 routing-ready primary services
- 2,851,425 origin-service pairs
- 1,536,775 reachable pairs (53.895%)
- 1,314,650 explicitly unreachable pairs
- 282 origins with zero reachable services
- zero duplicate pairs
- zero negative network times
- zero unreachable rows containing imputed travel times
- maximum travel-time arithmetic error below `1e-6` minute

## Interpretation boundary

This closure validates the operational reference network and its OD matrix. It does not convert cartographic distance into time, fabricate flood/dry scenarios, impute unreachable pairs, include waiting time, or enable ordinary-access air routing. It does not yet report final E2SFCA or formal structural-audit results.

The complete per-origin and per-service reachability summaries remain in the checksum-addressed closure artifact. Compact permanent audit records are stored in this directory.
