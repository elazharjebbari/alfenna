from django.db import models

class GalleryManager(models.Manager):
    def get_by_natural_key(self, slug):
        return self.get(slug=slug)

class Gallery(models.Model):
    """
    Conteneur d'items (participants/réalisations).
    DB-first : titres/preuves/CTA sont gérés ici et surchargés au besoin par la config.
    """
    objects = GalleryManager()

    slug = models.SlugField(unique=True)
    title = models.CharField(max_length=255, blank=True, default="")
    subtitle = models.CharField(max_length=500, blank=True, default="")
    proofs = models.JSONField(default=list, blank=True)  # [{icon, text}]
    cta_label = models.CharField(max_length=120, blank=True, default="Voir plus de réalisations")
    lightbox_enabled = models.BooleanField(default=True)
    anchor_id = models.SlugField(max_length=80, blank=True, default="galerie")
    product_code = models.CharField(
        max_length=64, blank=True, default="", help_text="Code produit/slug pour filtrer côté hydrateur"
    )
    is_active = models.BooleanField(default=True)
    namespace = models.CharField(max_length=50, blank=True, default="core")

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Galerie"
        verbose_name_plural = "Galeries"

    def __str__(self):
        return self.slug

    def natural_key(self):
        return (self.slug,)


class GalleryItem(models.Model):
    """
    Élément de la grille. Les URLs d'images sont relatives au STATIC_URL pour coller à ton existant.
    """
    gallery = models.ForeignKey(Gallery, related_name="items", on_delete=models.CASCADE)

    name = models.CharField(max_length=120)
    badge = models.CharField(max_length=60, blank=True, default="Participante")
    meta = models.CharField(max_length=255, blank=True, default="")
    alt = models.CharField(max_length=255, blank=True, default="")
    caption = models.CharField(max_length=255, blank=True, default="")

    # Chemins relatifs au dossier static (ex: "lumiereacademy/img/testimonial-lp/photo1.jpg")
    image = models.CharField(max_length=300)              # <img src>
    webp = models.CharField(max_length=300, blank=True)   # <source srcset>
    href = models.CharField(max_length=300, blank=True)   # lien lightbox sinon fallback image

    lang_code = models.CharField(max_length=10, blank=True, default="fr")
    year = models.CharField(max_length=10, blank=True, default="")
    product_code = models.CharField(max_length=64, blank=True, default="")

    sort_order = models.PositiveIntegerField(default=0)
    is_published = models.BooleanField(default=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Élément de galerie"
        verbose_name_plural = "Éléments de galerie"
        ordering = ("sort_order", "id")
        indexes = [
            models.Index(fields=["gallery", "is_published"]),
            models.Index(fields=["product_code"]),
        ]

    def __str__(self):
        return f"{self.name} ({self.gallery.slug})"

    @property
    def effective_href(self):
        return self.href or self.image
