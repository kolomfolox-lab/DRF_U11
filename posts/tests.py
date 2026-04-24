from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APIClient
from rest_framework import status
from django.contrib.auth.models import User
from .models import Post

class PostAPITestCase(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(username='testuser', password='password123')
        self.post = Post.objects.create(author=self.user, title='Test Post', content='Test content 10+ chars')

    def test_list_posts(self):
        url = reverse('post-list')
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_create_post_unauthenticated(self):
        url = reverse('post-list')
        response = self.client.post(url, {'title': 'New', 'content': 'Short'})
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
