# Free Data Sources

## Cricsheet

Use Cricsheet as the historical cricket backbone.

Useful downloads:

- `https://cricsheet.org/downloads/t20s_json.zip`
- `https://cricsheet.org/downloads/t20s_csv2.zip`

Planned derived tables:

- matches
- innings
- deliveries
- batting phase stats
- bowling phase stats
- venue par scores
- team Elo by format
- player form windows

## Open-Meteo

Use Open-Meteo for weather features:

- temperature
- humidity
- precipitation probability
- wind speed

Weather should be stored as raw JSON first, then mapped to fixtures by venue and start time.

## The Odds API

The Odds API can provide limited current odds snapshots on its free tier. It is not a free historical odds source.

The app should capture odds repeatedly and store them locally:

- timestamp
- market
- selection
- bookmaker/exchange
- decimal odds
- fixture mapping confidence

## Local Odds History

Your own odds snapshot table is one of the most important assets. Model validation should compare:

- model probability vs result
- model fair odds vs available odds
- taken price vs closing price
- edge buckets vs realised ROI
