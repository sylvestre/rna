# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

from datetime import datetime

from django import forms
from django.contrib import admin
from pagedown.widgets import AdminPagedownWidget

# For the display of the images
from django.utils.safestring import mark_safe
from django.contrib.admin.widgets import AdminFileWidget

from . import models


class AdminImageWidget(AdminFileWidget):
    """subclass the AdminFileWidget in order to display the image"""
    def render(self, name, value, attrs=None):
        output = []
        if value:
            output.append(u'<div>{0} size: {1}x{2}</div>'.format(value, value.width, value.height))
        output.append(super(AdminFileWidget, self).render(name, value, attrs))
        if value and getattr(value, "url", None):
            img = u'<div><img src="{0}" height="128px"/></div>'.format(value.url)
            output.append(img)
        return mark_safe(u''.join(output))


class NoteAdminForm(forms.ModelForm):
    note = forms.CharField(widget=AdminPagedownWidget())

    class Meta:
        model = models.Note


class NoteAdmin(admin.ModelAdmin):
    form = NoteAdminForm
    filter_horizontal = ['releases']
    list_display = ('id', 'bug', 'tag', 'note', 'created')
    list_display_links = ('id',)
    list_filter = ('tag', 'is_known_issue', 'releases__product',
                   'releases__version')
    search_fields = ('bug', 'note', 'releases__version')

    def formfield_for_dbfield(self, db_field, **kwargs):
        if db_field.name == 'image':  # The model has an 'image' field
            kwargs['widget'] = AdminImageWidget
            kwargs.pop('request', None)  # Error otherwise
            return db_field.formfield(**kwargs)
        return super(NoteAdmin, self).formfield_for_dbfield(db_field, **kwargs)


class ReleaseAdminForm(forms.ModelForm):
    system_requirements = forms.CharField(widget=AdminPagedownWidget(),
                                          required=False)
    text = forms.CharField(widget=AdminPagedownWidget(), required=False)
    release_date = forms.DateTimeField(widget=admin.widgets.AdminDateWidget)

    class Meta:
        model = models.Release


class ReleaseAdmin(admin.ModelAdmin):
    actions = ['copy_releases']
    form = ReleaseAdminForm
    list_display = ('version', 'product', 'channel', 'is_public',
                    'release_date', 'text', 'url')
    list_filter = ('product', 'channel', 'is_public')
    ordering = ('-release_date',)
    search_fields = ('version', 'text')

    def url(self, obj):
        base_url_staging = "https://www-dev.allizom.org/en-US"
        base_url_prod = "https://www.mozilla.com/en-US"
        product = ""

        if obj.product == "Firefox for Android":
            product = "mobile"
        elif obj.product == "Firefox" or obj.product == "Firefox Extended Support Release":
            product = "firefox"
        elif obj.product == "Thunderbird":
            product = "thunderbird"
        elif obj.product == "Firefox OS":
            # Special case for Firefox OS. URL are different
            return ('<a href="{staging}/firefox/os/notes/{version}/">Staging</a> / '
                    '<a href="{prod}/firefox/os/notes/{version}/">Public</a>'.format(
                        staging=base_url_staging, product=product, version=obj.version, prod=base_url_prod))

        return ('<a href="{staging}/{product}/{version}/releasenotes/">Staging</a> / '
                '<a href="{prod}/{product}/{version}/releasenotes/">Public</a>'.format(
                    staging=base_url_staging, product=product, version=obj.version, prod=base_url_prod))

    url.allow_tags = True

    def copy_releases(self, request, queryset):
        release_count = 0
        for release in queryset:
            release_count += 1
            copy_count = self.model.objects.filter(
                version__endswith=release.version,
                product=release.product).count()
            notes = list(release.note_set.all())
            copy = release
            copy.id = None
            if copy_count > 1:
                copy.version = 'copy%s-%s' % (copy_count, copy.version)
            else:
                copy.version = 'copy-' + copy.version
            # By default, set it to public. Usually, the copy feature is used
            # when copying aurora => beta or beta => release. We want to review
            # it before going live
            copy.is_public = False
            copy.save()
            copy.note_set.add(*notes)
            copy.note_set.update(modified=datetime.now())
        if release_count == 1:
            self.message_user(request, 'Copied Release')
        else:
            self.message_user(request, 'Copied %s Releases' % release_count)


admin.site.register(models.Note, NoteAdmin)
admin.site.register(models.Release, ReleaseAdmin)
