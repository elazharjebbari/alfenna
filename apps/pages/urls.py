from django.urls import path, reverse
from django.views.generic import RedirectView

from .views import HomeView, TestView, ContactView, CoursesView, CourseDetailView, LoginViewSafe, PacksView, DemoView, FaqView, ProductDetailView
from apps.accounts.views import (
    SignupView,
    PasswordResetRequestView,
    PasswordResetDoneViewCustom,
    PasswordResetCompleteViewCustom,
    CheckEmailView,
    VerificationSuccessView,
    VerificationErrorView,
)
from .views.views_lecture import LearnCourseView
from .views.views_billing import CheckoutOrchestratorView, ThankYouView


class CheckoutLegacyRedirectView(RedirectView):
    permanent = False

    def get_redirect_url(self, *args, **kwargs):
        plan_slug = (self.request.GET.get("plan") or "").strip() or kwargs.get("slug")
        if not plan_slug:
            return None
        return reverse("pages:checkout", kwargs={"plan_slug": plan_slug})


class LectureStreamRedirectView(RedirectView):
    permanent = False

    def get_redirect_url(self, *args, **kwargs):
        pk = kwargs.get("pk")
        if pk is None:
            return None
        return reverse("learning:stream", args=[pk])


class DemoDefaultRedirectView(RedirectView):
    permanent = False

    def get_redirect_url(self, *args, **kwargs):
        return reverse("pages:demo", kwargs={"course_slug": "bougies-naturelles"})

app_name = "pages"
urlpatterns = [
                  path("", HomeView.as_view(), name="home"),  # = onlinelearning-home
                  path("demo/", DemoDefaultRedirectView.as_view(), name="demo-default"),
                  path("demo/<slug:course_slug>/", DemoView.as_view(), name="demo"),
                  path("contact", ContactView.as_view(), name="contact"),
                  path("courses", CoursesView.as_view(), name="courses"),
                  path("learn/", CoursesView.as_view(), name="learn"),
                  path("test", TestView.as_view(), name="test"),  # test
                  path("packs", PacksView.as_view(), name="packs"),  # test
                  path("faq/", FaqView.as_view(), name="faq"),
                  path("produits/", ProductDetailView.as_view(), name="product-detail"),
                  path("produits/<slug:product_slug>/", ProductDetailView.as_view(), name="product-detail-slug"),
                  path("course-detail/<slug:course_slug>/", CourseDetailView.as_view(), name="course-detail"),
                  path("learn/<int:pk>/", LectureStreamRedirectView.as_view(), name="lecture-stream"),
                  path("learn/<slug:course_slug>/", LearnCourseView.as_view(), name="lecture"),
                  path("learn/<slug:course_slug>/<slug:lecture_slug>/", LearnCourseView.as_view(), name="lecture-detail"),
              ] + [
                  path("login/", LoginViewSafe.as_view(), name="login"),
                  path("inscription/", SignupView.as_view(), name="register"),
                  path("inscription/check-email/", CheckEmailView.as_view(), name="check_email"),
                  path("verification/succes/", VerificationSuccessView.as_view(), name="verification_success"),
                  path("verification/erreur/", VerificationErrorView.as_view(), name="verification_error"),
                  path("mot-de-passe-oublie/", PasswordResetRequestView.as_view(), name="password_reset_request"),
                  path("mot-de-passe-oublie/envoye/", PasswordResetDoneViewCustom.as_view(), name="password_reset_done"),
                  path("mot-de-passe-oublie/termine/", PasswordResetCompleteViewCustom.as_view(), name="password_reset_complete"),
                  path("billing/checkout/plan/<slug:plan_slug>/", CheckoutOrchestratorView.as_view(), name="checkout"),
                  path("billing/thank-you/plan/<slug:plan_slug>/", ThankYouView.as_view(), name="thank-you"),
                  path("billing/checkout/<slug:slug>/", CheckoutLegacyRedirectView.as_view(), name="checkout-legacy"),
              ]
