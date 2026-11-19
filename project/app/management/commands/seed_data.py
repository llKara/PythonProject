from datetime import datetime, time, timedelta
from decimal import Decimal

from django.contrib.auth.models import User
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from app.models import (
    UserProfile,
    Farm,
    Category,
    PackagingType,
    Product,
    SupplyBatch,
    BatchProduct,
    PreOrder,
    OrderItem,
    WeightAdjustment,
    Delivery,
)


class Command(BaseCommand):
    help = "Заполняет базу тестовыми данными для магазина фермерских продуктов"

    def add_arguments(self, parser):
        parser.add_argument(
            "--clear",
            action="store_true",
            help="Удалить данные из таблиц проекта перед заполнением",
        )

    @transaction.atomic
    def handle(self, *args, **options):
        if options["clear"]:
            self.clear_data()

        customers = self.create_profiles("customer", "Покупатель", 10)
        farmers = self.create_profiles("farmer", "Фермер-поставщик", 5)
        pickers = self.create_profiles("picker", "Комплектовщик", 1)
        couriers = self.create_profiles("courier", "Курьер", 1)
        self.create_profiles("admin", "Администратор", 1)

        categories = self.create_categories()
        packaging_types = self.create_packaging_types()
        farms = self.create_farms(farmers)

        products = self.create_products(farms, categories, packaging_types)
        batches = self.create_batches(farms)
        batch_products = self.create_batch_products(batches, products)

        orders = self.create_orders(customers, batches, batch_products)
        self.create_weight_adjustments(orders, pickers[0])
        self.create_deliveries(orders, couriers[0], batches)

        self.show_counts()

    def clear_data(self):
        WeightAdjustment.objects.all().delete()
        Delivery.objects.all().delete()
        OrderItem.objects.all().delete()
        PreOrder.objects.all().delete()
        BatchProduct.objects.all().delete()
        SupplyBatch.objects.all().delete()
        Product.objects.all().delete()
        Farm.objects.all().delete()
        Category.objects.all().delete()
        PackagingType.objects.all().delete()
        UserProfile.objects.all().delete()
        User.objects.filter(username__startswith="seed_").delete()
        User.objects.filter(username__startswith="test_").delete()

        self.stdout.write(self.style.WARNING(
            "Старые данные из таблиц проекта удалены."
        ))

    def create_profiles(self, role, title, amount):
        profiles = []

        for number in range(1, amount + 1):
            username = f"seed_{role}_{number:02d}"

            user, created = User.objects.get_or_create(
                username=username,
                defaults={
                    "first_name": f"{title} {number}",
                    "email": f"{username}@example.com",
                },
            )

            if created:
                user.set_password("test12345")
                user.save()

            profile, _ = UserProfile.objects.update_or_create(
                user=user,
                defaults={
                    "role": role,
                    "phone": f"+7999000{len(profiles) + 1:04d}",
                    "default_address": "",
                },
            )
            profiles.append(profile)

        return profiles

    def create_categories(self):
        names = [
            "Овощи",
            "Фрукты",
            "Ягоды",
            "Молочные продукты",
            "Мясо",
            "Зелень",
        ]

        categories = []
        for name in names:
            category, _ = Category.objects.get_or_create(
                name=name,
                defaults={"description": f"Продукты категории «{name}»"},
            )
            categories.append(category)

        return categories

    def create_packaging_types(self):
        data = [
            ("Штучный", "piece", "шт."),
            ("Весовой", "weight", "кг"),
        ]

        packaging_types = []
        for name, code, unit in data:
            packaging, _ = PackagingType.objects.get_or_create(
                code=code,
                defaults={"name": name, "unit": unit},
            )
            packaging_types.append(packaging)

        return packaging_types

    def create_farms(self, farmers):
        farms = []

        for number, farmer in enumerate(farmers, start=1):
            farm, _ = Farm.objects.get_or_create(
                name=f"Тестовое фермерское хозяйство №{number}",
                defaults={
                    "owner": farmer,
                    "description": f"Фермерское хозяйство №{number}",
                    "phone": f"+7999111{number:04d}",
                    "email": f"farm{number}@example.com",
                    "address": f"Россия, тестовая область, деревня №{number}",
                },
            )
            farms.append(farm)

        return farms

    def create_products(self, farms, categories, packaging_types):
        names = [
            "Картофель", "Морковь", "Свёкла", "Капуста", "Лук", "Огурцы",
            "Яблоки", "Груши", "Сливы", "Персики", "Абрикосы", "Вишня",
            "Клубника", "Малина", "Смородина", "Черника", "Ежевика", "Крыжовник",
            "Молоко", "Творог", "Сметана", "Сыр", "Кефир", "Йогурт",
            "Говядина", "Свинина", "Курица", "Индейка", "Укроп", "Петрушка",
        ]

        products = []
        for index, name in enumerate(names):
            farm_index = index // 6
            farm = farms[farm_index]
            category = categories[index % len(categories)]
            packaging = packaging_types[index % len(packaging_types)]

            product, _ = Product.objects.get_or_create(
                farm=farm,
                name=name,
                defaults={
                    "category": category,
                    "packaging_type": packaging,
                    "description": f"Свежий фермерский продукт: {name.lower()}",
                    "price": Decimal("100.00") + Decimal(index * 5),
                    "image": "",
                    "is_active": True,
                },
            )
            products.append(product)

        return products

    def create_batches(self, farms):
        batches = []
        first_day = timezone.localdate() + timedelta(days=14)

        for farm_index, farm in enumerate(farms):
            for batch_number in range(3):
                arrival_day = first_day + timedelta(days=batch_number * 7)
                arrival_naive = datetime.combine(arrival_day, time(10, 0))
                arrival = timezone.make_aware(arrival_naive)

                batch, _ = SupplyBatch.objects.get_or_create(
                    farm=farm,
                    arrival_at=arrival,
                    defaults={"status": "planned"},
                )
                batches.append(batch)

        return batches

    def create_batch_products(self, batches, products):
        batch_products = []

        for batch_index, batch in enumerate(batches):
            farm_product_start = (batch_index // 3) * 6
            farm_products = products[farm_product_start:farm_product_start + 6]

            for product in farm_products:
                batch_product, _ = BatchProduct.objects.get_or_create(
                    batch=batch,
                    product=product,
                    defaults={
                        "available_limit": Decimal("100.000"),
                        "reserved_quantity": Decimal("0.000"),
                    },
                )
                batch_products.append(batch_product)

        return batch_products

    def create_orders(self, customers, batches, batch_products):
        orders = []
        items = []

        for index, customer in enumerate(customers):
            batch = batches[index]
            order, _ = PreOrder.objects.get_or_create(
                customer=customer,
                arrival_at=batch.arrival_at,
                defaults={
                    "status": PreOrder.STATUS_CHOICES[index % 5][0],
                    "preliminary_total": Decimal("0.00"),
                    "final_total": Decimal("0.00"),
                },
            )

            start = index * 6
            order_batch_products = batch_products[start:start + 3]
            total = Decimal("0.00")

            for position, batch_product in enumerate(order_batch_products):
                quantity = Decimal("1.000") + Decimal(position)
                actual_quantity = (
                    quantity * Decimal("1.05")
                ).quantize(Decimal("0.001"))

                item, _ = OrderItem.objects.get_or_create(
                    order=order,
                    batch_product=batch_product,
                    defaults={
                        "quantity": quantity,
                        "actual_quantity": actual_quantity,
                        "unit_price": batch_product.product.price,
                        "is_picked": True,
                    },
                )

                total += item.unit_price * item.actual_quantity
                items.append(item)

            order.preliminary_total = total.quantize(Decimal("0.01"))
            order.final_total = total.quantize(Decimal("0.01"))
            order.save(update_fields=["preliminary_total", "final_total"])
            orders.append(order)

        return orders

    def create_weight_adjustments(self, orders, picker):
        items = OrderItem.objects.filter(order__in=orders).order_by("id")[:8]

        for item in items:
            WeightAdjustment.objects.get_or_create(
                order_item=item,
                defaults={
                    "edited_by": picker,
                    "reason": "Корректировка фактического веса при сборке",
                },
            )

    def create_deliveries(self, orders, courier, batches):
        for index, order in enumerate(orders[:5]):
            batch = batches[index]

            Delivery.objects.get_or_create(
                order=order,
                defaults={
                    "courier": courier,
                    "address": f"Россия, тестовый адрес покупателя №{index + 1}",
                    "interval_start": batch.arrival_at + timedelta(hours=2),
                    "interval_end": batch.arrival_at + timedelta(hours=4),
                    "status": "waiting",
                },
            )

    def show_counts(self):
        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS("Количество тестовых записей:"))
        self.stdout.write(f"Продукты: {Product.objects.count()}")
        self.stdout.write(f"Фермерские хозяйства: {Farm.objects.count()}")
        self.stdout.write(f"Категории: {Category.objects.count()}")
        self.stdout.write(f"Типы фасовки: {PackagingType.objects.count()}")
        self.stdout.write(f"Партии поставки: {SupplyBatch.objects.count()}")
        self.stdout.write(f"Продукты в партиях: {BatchProduct.objects.count()}")
        self.stdout.write(f"Пользователи: {UserProfile.objects.count()}")
        self.stdout.write(f"Предзаказы: {PreOrder.objects.count()}")
        self.stdout.write(f"Позиции предзаказов: {OrderItem.objects.count()}")
        self.stdout.write(f"Корректировки веса: {WeightAdjustment.objects.count()}")
        self.stdout.write(f"Доставки: {Delivery.objects.count()}")