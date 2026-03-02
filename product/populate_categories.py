import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'product.settings')
django.setup()

from myapp.models import Category

def update_categories():
    print("\n" + "="*60)
    print("UPDATING CAMPUSKART CATEGORIES")
    print("="*60)
    
    # Delete all existing categories
    deleted_count = Category.objects.all().delete()[0]
    print(f"✅ Deleted {deleted_count} existing categories")
    
    # Your desired categories (without Fiction Books)
    desired_categories = [
        {'name': 'Textbooks', 'slug': 'textbooks', 'icon': 'fas fa-book'},
        {'name': 'Electronics', 'slug': 'electronics', 'icon': 'fas fa-microchip'},
        {'name': 'Lab Equipment', 'slug': 'lab-equipment', 'icon': 'fas fa-flask'},
        {'name': 'Sports Equipment', 'slug': 'sports-equipment', 'icon': 'fas fa-futbol'},
        {'name': 'Notes', 'slug': 'notes', 'icon': 'fas fa-pen'},
        {'name': 'Stationery', 'slug': 'stationery', 'icon': 'fas fa-pencil-alt'},
    ]
    
    print("\n📝 Creating new categories:")
    print("-" * 40)
    
    for cat in desired_categories:
        Category.objects.create(
            name=cat['name'],
            slug=cat['slug'],
            icon=cat['icon']
        )
        print(f"   ✅ Created: {cat['name']}")
    
    print("-" * 40)
    print(f"\n📊 Total categories: {Category.objects.count()}")
    
    print("\n📋 Your final categories:")
    for cat in Category.objects.all().order_by('name'):
        print(f"   • {cat.name}")
    
    print("\n" + "="*60)
    print("✅ CATEGORY UPDATE COMPLETE!")
    print("="*60)

if __name__ == "__main__":
    update_categories()