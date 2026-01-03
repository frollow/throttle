from ads_throttle.throttling import should_show_ads


def ads(request):
    return {"show_ads": should_show_ads(request)}
