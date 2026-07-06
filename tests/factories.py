import factory
from django.contrib.auth import get_user_model

from apps.posts.models import Post

User = get_user_model()


class UserFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = User
        skip_postgeneration_save = True

    email = factory.Sequence(lambda n: f"user{n}@example.com")
    username = factory.Sequence(lambda n: f"user{n}")
    full_name = factory.Faker("name")
    is_verified = True
    password = factory.django.Password("password123")


class PostFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Post

    author = factory.SubFactory(UserFactory)
    title = factory.Sequence(lambda n: f"Post title {n}")
    content = factory.Faker("paragraph")
