# Unit Conversion & Package-Size Normalisation

Raw package strings such as `5KG`, `380ML` or `24 x 25g` cannot be compared
arithmetically. Before any elementary price aggregation the pipeline converts
each observation to a **base metric unit price** (`KHR / kg` or `KHR / l`).

## Where this happens

- `int_prices_cleaned.sql` parses the raw `package_size` into `size_value` +
  `size_unit` using regex patterns, normalises the unit to a canonical code
  (`kg`, `g`, `l`, `ml`), and computes `unit_price_khr`:

  ```
  unit_price_khr =
      price_khr / size_value            when size_unit in ('kg', 'l')
      price_khr / (size_value / 1000)   when size_unit in ('g', 'ml')
  ```

- `clean_store_prices.sql` and `gold.fct_daily_prices` carry `size_value`,
  `size_unit`, and `unit_price_khr` forward for metric unit price comparisons.

## Guarantees enforced by tests

- `test_unit_math.sql` asserts that when a parseable size exists,
  `unit_price_khr` equals `price_khr / normalised_size` within rounding.
- Prices are always compared in KHR (`int_prices_cleaned.price_khr`); USD is
  converted at the MEF daily rate with a documented 4044 fallback.

## Known limitations

- Pack quantities (`24 x 25g`) are not yet split into per-unit sizes; the
  pack-level price is used and `pack_qty` is fixed at 1.
- Unparseable sizes (`has_unparsed_size = TRUE`) keep a NULL unit price and are
  excluded from unit-price comparisons (fall back to pack price).
