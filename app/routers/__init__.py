from . import best9, clusters, comments, misc, search, streamers, vods

ALL_ROUTERS = [
    comments.router,
    vods.router,
    streamers.router,
    best9.router,
    search.router,
    clusters.router,
    misc.router,
]
