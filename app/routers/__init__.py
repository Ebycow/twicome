from . import best9, clusters, comments, misc, quiz, search, stats, streamers, vods

ALL_ROUTERS = [
    comments.router,
    vods.router,
    streamers.router,
    best9.router,
    search.router,
    stats.router,
    clusters.router,
    quiz.router,
    misc.router,
]
