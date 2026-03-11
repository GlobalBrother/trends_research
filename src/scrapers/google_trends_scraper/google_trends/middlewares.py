import random


class RandomUserAgentMiddleware:
    def __init__(self, user_agents):
        self.user_agents = user_agents or []
        self.selected_user_agent = random.choice(self.user_agents) if self.user_agents else None

    @classmethod
    def from_crawler(cls, crawler):
        return cls(user_agents=crawler.settings.get('USER_AGENTS'))

    def process_request(self, request, spider):
        if self.selected_user_agent:
            request.headers.setdefault('User-Agent', self.selected_user_agent)


class ProxyMiddleware:
    def __init__(self, proxy_list):
        self.proxy_list = proxy_list or []
        self.proxy_index = 0

    @classmethod
    def from_crawler(cls, crawler):
        return cls(proxy_list=crawler.settings.get('PROXY_LIST'))

    def process_request(self, request, spider):
        if self.proxy_list:
            proxy = self.proxy_list[self.proxy_index]
            self.proxy_index = (self.proxy_index + 1) % len(self.proxy_list)
            request.meta['proxy'] = proxy
            request.meta.setdefault('cookiejar', proxy)
        else:
            request.meta.setdefault('cookiejar', 'default')