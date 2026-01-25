# drafts/urls.py
from django.urls import include, path
from .views import DraftCreateView, DraftDetailView, DraftUpdateView
from .api import ChampionListView, TeamListView, DraftRecommendationView, DraftSimilarMatchesView

urlpatterns = [
    path("drafts/", DraftCreateView.as_view()),
    path("drafts/<uuid:draft_id>/", DraftDetailView.as_view()),
    path("drafts/<uuid:draft_id>/update/", DraftUpdateView.as_view()),
    path("champions/", ChampionListView.as_view()),
    path("teams/", TeamListView.as_view()),
    path("recommendations/", DraftRecommendationView.as_view()),
    path("similar-matches/", DraftSimilarMatchesView.as_view()),
]
