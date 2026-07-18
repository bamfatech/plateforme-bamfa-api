from django.test.utils import isolate_apps

from apps.common.models import PublishableMixin


@isolate_apps("tests")
def test_publish_et_unpublish():
    class Article(PublishableMixin):
        class Meta:
            app_label = "tests"

    article = Article()
    assert article.status == PublishableMixin.Status.BROUILLON
    assert article.is_published is False

    article.publish()
    assert article.status == PublishableMixin.Status.PUBLIE
    assert article.published_at is not None
    assert article.is_published is True

    article.unpublish()
    assert article.status == PublishableMixin.Status.DEPUBLIE
    assert article.is_published is False
