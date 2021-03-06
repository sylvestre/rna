# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

from datetime import datetime

from django.conf import settings
from django.db import models
from django_extensions.db.fields import CreationDateTimeField


class TimeStampedModel(models.Model):
    """
    Replacement for django_extensions.db.models.TimeStampedModel
    that updates the modified timestamp by default, but allows
    that behavior to be overridden by passing a modified=False
    parameter to the save method
    """
    created = CreationDateTimeField()
    modified = models.DateTimeField(editable=False, blank=True, db_index=True)

    class Meta:
        abstract = True

    def save(self, *args, **kwargs):
        if kwargs.pop('modified', True):
            self.modified = datetime.now()
        super(TimeStampedModel, self).save(*args, **kwargs)


class Release(TimeStampedModel):
    CHANNELS = ('Nightly', 'Aurora', 'Beta', 'Release', 'ESR')
    PRODUCTS = ('Firefox', 'Firefox for Android',
                'Firefox Extended Support Release', 'Firefox OS',
                'Thunderbird')

    product = models.CharField(max_length=255,
                               choices=[(p, p) for p in PRODUCTS])
    channel = models.CharField(max_length=255,
                               choices=[(c, c) for c in CHANNELS])
    version = models.CharField(max_length=255)
    release_date = models.DateTimeField()
    text = models.TextField(blank=True)
    is_public = models.BooleanField(default=False)
    bug_list = models.TextField(blank=True)
    bug_search_url = models.CharField(max_length=2000, blank=True)
    system_requirements = models.TextField(blank=True)

    def major_version(self):
        return self.version.split('.', 1)[0]

    def get_bug_search_url(self):
        if self.bug_search_url:
            return self.bug_search_url

        if self.product == 'Thunderbird':
            return (
                'https://bugzilla.mozilla.org/buglist.cgi?'
                'classification=Client%20Software&query_format=advanced&'
                'bug_status=RESOLVED&bug_status=VERIFIED&bug_status=CLOSED&'
                'target_milestone=Thunderbird%20{version}.0&product=Thunderbird'
                '&resolution=FIXED'
            ).format(version=self.major_version())

        return (
            'https://bugzilla.mozilla.org/buglist.cgi?'
            'j_top=OR&f1=target_milestone&o3=equals&v3=Firefox%20{version}&'
            'o1=equals&resolution=FIXED&o2=anyexact&query_format=advanced&'
            'f3=target_milestone&f2=cf_status_firefox{version}&'
            'bug_status=RESOLVED&bug_status=VERIFIED&bug_status=CLOSED&'
            'v1=mozilla{version}&v2=fixed%2Cverified&limit=0'
        ).format(version=self.major_version())

    def equivalent_release_for_product(self, product):
        """
        Returns the release for a specified product with the same
        channel and major version with the highest minor version,
        or None if no such releases exist
        """
        releases = self._default_manager.filter(
            version__startswith=self.major_version() + '.',
            channel=self.channel, product=product).order_by('-version')
        if not getattr(settings, 'DEV', False):
            releases = releases.filter(is_public=True)
        if releases:
            return sorted(
                sorted(releases, reverse=True,
                       key=lambda r: len(r.version.split('.'))),
                reverse=True, key=lambda r: r.version.split('.')[1])[0]

    def equivalent_android_release(self):
        if self.product == 'Firefox':
            return self.equivalent_release_for_product('Firefox for Android')

    def equivalent_desktop_release(self):
        if self.product == 'Firefox for Android':
            return self.equivalent_release_for_product('Firefox')

    def notes(self, public_only=False):
        """
        Retrieve a list of Note instances that should be shown for this
        release, grouped as either new features or known issues, and sorted
        first by sort_num highest to lowest, which is applied to both groups,
        and then for new features we also sort by tag in the order specified
        by Note.TAGS, with untagged notes coming first, then finally moving
        any note with the fixed tag that starts with the release version to
        the top, for what we call "dot fixes".
        """
        tag_index = dict((tag, i) for i, tag in enumerate(Note.TAGS))
        notes = self.note_set.order_by('-sort_num')
        if public_only:
            notes = notes.filter(is_public=True)
        known_issues = [n for n in notes if n.is_known_issue_for(self)]
        new_features = sorted(
            sorted(
                (n for n in notes if not n.is_known_issue_for(self)),
                key=lambda note: tag_index.get(note.tag, 0)),
            key=lambda n: n.tag == 'Fixed' and n.note.startswith(self.version),
            reverse=True)

        return new_features, known_issues

    def __unicode__(self):
        return '{product} {version} {channel}'.format(
            product=self.product, version=self.version, channel=self.channel)

    class Meta:
        # TODO: see if this has a significant performance impact
        ordering = ('product', '-version', 'channel')
        unique_together = (('product', 'version'),)


class Note(TimeStampedModel):
    TAGS = ('New', 'Changed', 'HTML5', 'Feature', 'Language', 'Developer',
            'Fixed')

    bug = models.IntegerField(null=True, blank=True)
    note = models.TextField(blank=True)
    releases = models.ManyToManyField(Release, blank=True)
    is_known_issue = models.BooleanField(default=False)
    fixed_in_release = models.ForeignKey(Release, null=True, blank=True,
                                         related_name='fixed_note_set')
    tag = models.CharField(max_length=255, blank=True,
                           choices=[(t, t) for t in TAGS])
    sort_num = models.IntegerField(default=0)
    is_public = models.BooleanField(default=True)

    image = models.ImageField(upload_to=lambda instance, filename: '/'.join(['screenshot', str(instance.pk), filename]))

    def is_known_issue_for(self, release):
        return self.is_known_issue and self.fixed_in_release != release

    def __unicode__(self):
        return self.note
