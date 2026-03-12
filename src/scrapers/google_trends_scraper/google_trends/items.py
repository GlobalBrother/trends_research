import scrapy

class GoogleTrendItem(scrapy.Item):
    keyword = scrapy.Field()
    geo = scrapy.Field()
    time_range = scrapy.Field()
    category = scrapy.Field()
    data_type = scrapy.Field()  # interest_over_time, related_queries, related_topics, trending_searches
    results = scrapy.Field()    # List of trend points or related items
    extracted_at = scrapy.Field()

class ScrapeErrorItem(scrapy.Item):
    platform = scrapy.Field()
    keyword = scrapy.Field()
    url = scrapy.Field()
    status = scrapy.Field()
    reason = scrapy.Field()
    extracted_at = scrapy.Field()
