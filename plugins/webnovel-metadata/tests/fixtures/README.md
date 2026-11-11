# Parser fixtures

These compact fixtures reproduce structures observed on the official public pages
in November 2026. Titles, authors and synopsis text are invented test data. They
are **not** complete saved webpages and passing these tests does not establish
current network availability.

- `qidian_desktop.html`: the user's existing webnovel-import desktop selectors.
- `qidian_mobile.html`: mobile OG tags, `Book` JSON-LD and the exact Vite SSR
  `pageContext.pageProps.pageData.bookInfo` path. The unrelated Book demonstrates
  that recommendations must not supply the requested book's fields.
- `qimao.html`: the public book-information block, including latest-chapter ID
  evidence when no canonical URL is present.
- `fanqie.html`: the public page header and Baidu JSON-LD signed cover, alongside
  the known grey loading placeholder and an author avatar that must be ignored.

Live verification results and environment limits belong in the plugin's
validation documentation, separately from these offline regression tests.
