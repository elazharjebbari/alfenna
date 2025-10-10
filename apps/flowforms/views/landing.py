from django.views.generic import TemplateView


class LandingFormView(TemplateView):
    template_name = "flowforms/landing_short.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["page_title"] = "Form Landing — 3 étapes"
        return ctx
