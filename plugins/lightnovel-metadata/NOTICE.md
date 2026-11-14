# Data source and attribution notices

The plugin implements interoperability with the following public bibliographic services. No external source code is copied into this plugin.

- Bangumi: https://bangumi.github.io/api/ (subject API; rights and site rules apply)
- 博客来 Books.com.tw: https://www.books.com.tw/ (product metadata pages; automated access rules apply)
- openBD: https://openbd.jp/ (book-oriented metadata API, usage conditions at openBD)
- National Diet Library Search: https://ndlsearch.ndl.go.jp/help/api (bibliographic OpenSearch)

Source text, covers, publisher data and branding may be subject to separate copyrights and use policies. This code does not grant redistribution rights for third-party assets. Do not ignore site rate limits, authentication or access restrictions.

The product architecture was informed by the author's CalibrePlugins, Bangumi-sync and MangaTag projects. No dependencies on those applications are required at runtime.

Additional optional sources in v0.2.0:
- 台灣角川 (Taiwan KADOKAWA): https://www.kadokawa.com.tw/ (public product metadata; site policies apply)
- 尖端出版 (SPP): https://www.spp.com.tw/ (public product metadata; site policies apply)
- National Central Library, Taiwan: https://data.gov.tw/dataset/6730 (monthly prepublication CSV; Taiwan Open Government Data License v1.0 applies to the data)

The NCL importer reads a user-downloaded local CSV. It does not crawl or redistribute the database. Its prepublication dates do not assert actual publication.
