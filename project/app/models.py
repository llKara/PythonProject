from datetime import timedelta
from decimal import Decimal

from django.contrib.auth.models import User
from django.db import models
from django.db.models import F, Q
from django.utils import timezone


class UserProfile(models.Model):
    ROLE_CHOICES = [
        ("customer", "Покупатель"),
        ("farmer", "Фермер-поставщик"),
        ("picker", "Комплектовщик"),
        ("courier", "Курьер"),
        ("admin", "Администратор"),
    ]

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="profile", verbose_name="Учётная запись")
    role = models.CharField("Роль", max_length=20, choices=ROLE_CHOICES)
    phone = models.CharField("Телефон", max_length=20, blank=True)
    default_address = models.TextField("Адрес по умолчанию", blank=True)
    created_at = models.DateTimeField("Дата создания", auto_now_add=True)

    class Meta:
        verbose_name = "Пользователь"
        verbose_name_plural = "Пользователи"
        ordering = ["id"]

    def __str__(self):
        return self.user.username


class Farm(models.Model):
    owner = models.ForeignKey(UserProfile, on_delete=models.PROTECT, related_name="farms", verbose_name="Владелец хозяйства")
    name = models.CharField("Название хозяйства", max_length=150, unique=True)
    description = models.TextField("Описание", blank=True)
    phone = models.CharField("Телефон", max_length=20)
    email = models.EmailField("Электронная почта", blank=True)
    address = models.CharField("Адрес хозяйства", max_length=255)

    class Meta:
        verbose_name = "Фермерское хозяйство"
        verbose_name_plural = "Фермерские хозяйства"
        ordering = ["name"]

    def __str__(self):
        return self.name


class Category(models.Model):
    name = models.CharField("Название категории", max_length=80, unique=True)
    description = models.TextField("Описание", blank=True)

    class Meta:
        verbose_name = "Категория"
        verbose_name_plural = "Категории"
        ordering = ["name"]

    def __str__(self):
        return self.name


class PackagingType(models.Model):
    name = models.CharField("Название типа фасовки", max_length=30, unique=True)
    code = models.CharField("Код типа", max_length=10, unique=True)
    unit = models.CharField("Единица измерения", max_length=5)

    class Meta:
        verbose_name = "Тип фасовки"
        verbose_name_plural = "Типы фасовки"
        ordering = ["name"]

    def __str__(self):
        return self.name


class Product(models.Model):
    farm = models.ForeignKey(Farm, on_delete=models.PROTECT, related_name="products", verbose_name="Фермерское хозяйство")
    category = models.ForeignKey(Category, on_delete=models.PROTECT, related_name="products", verbose_name="Категория")
    packaging_type = models.ForeignKey(PackagingType, on_delete=models.PROTECT, related_name="products", verbose_name="Тип фасовки")
    name = models.CharField("Название продукта", max_length=150)
    description = models.TextField("Описание", blank=True)
    price = models.DecimalField("Цена за единицу", max_digits=10, decimal_places=2)
    image = models.CharField("Фотография", max_length=100, blank=True)
    is_active = models.BooleanField("Показывать в каталоге", default=True)
    created_at = models.DateTimeField("Дата добавления", auto_now_add=True)
    supply_batches = models.ManyToManyField(
        "SupplyBatch", through="BatchProduct", related_name="products", verbose_name="Партии поставки", blank=True
    )

    class Meta:
        verbose_name = "Продукт"
        verbose_name_plural = "Продукты"
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(fields=["farm", "name"], name="uq_product_farm_name"),
            models.CheckConstraint(condition=Q(price__gte=Decimal("0.01")), name="ck_product_price_positive"),
        ]

    def __str__(self):
        return self.name


class SupplyBatch(models.Model):
    STATUS_CHOICES = [
        ("planned", "Запланирована"),
        ("arrived", "Прибыла"),
        ("closed", "Закрыта"),
    ]

    farm = models.ForeignKey(Farm, on_delete=models.PROTECT, related_name="batches", verbose_name="Фермерское хозяйство")
    arrival_at = models.DateTimeField("Дата и время привоза")
    orders_close_at = models.DateTimeField("Закрытие приёма предзаказов", editable=False)
    status = models.CharField("Статус партии", max_length=12, choices=STATUS_CHOICES, default="planned")
    created_at = models.DateTimeField("Дата создания", auto_now_add=True)

    class Meta:
        verbose_name = "Партия поставки"
        verbose_name_plural = "Партии поставки"
        ordering = ["arrival_at"]
        constraints = [
            models.UniqueConstraint(fields=["farm", "arrival_at"], name="uq_farm_arrival")
        ]

    def save(self, *args, **kwargs):
        if self.arrival_at:
            self.orders_close_at = self.arrival_at - timedelta(hours=36)
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.farm.name} – {self.arrival_at:%d.%m.%Y %H:%M}"


class BatchProduct(models.Model):
    batch = models.ForeignKey(SupplyBatch, on_delete=models.CASCADE, related_name="batch_products", verbose_name="Партия поставки")
    product = models.ForeignKey(Product, on_delete=models.PROTECT, related_name="batch_products", verbose_name="Продукт")
    available_limit = models.DecimalField("Лимит партии", max_digits=10, decimal_places=3)
    reserved_quantity = models.DecimalField("Зарезервированное количество", max_digits=10, decimal_places=3, default=Decimal("0.000"))

    class Meta:
        verbose_name = "Продукт в партии"
        verbose_name_plural = "Продукты в партиях"
        ordering = ["batch_id", "product_id"]
        constraints = [
            models.UniqueConstraint(fields=["batch", "product"], name="uq_batch_product"),
            models.CheckConstraint(condition=Q(available_limit__gt=0), name="ck_batch_limit_positive"),
            models.CheckConstraint(condition=Q(reserved_quantity__gte=0), name="ck_batch_reserved_nonnegative"),
            models.CheckConstraint(condition=Q(reserved_quantity__lte=F("available_limit")), name="ck_batch_reserved_limit"),
        ]

    def __str__(self):
        return f"{self.product.name} – {self.batch}"


class PreOrder(models.Model):
    STATUS_CHOICES = [
        ("new", "Новый"),
        ("assembling", "Собирается"),
        ("assembled", "Собран"),
        ("out_for_delivery", "Передан курьеру"),
        ("completed", "Выполнен"),
        ("cancelled", "Отменён"),
    ]

    customer = models.ForeignKey(UserProfile, on_delete=models.PROTECT, related_name="preorders", verbose_name="Покупатель")
    arrival_at = models.DateTimeField("Дата и время привоза")
    created_at = models.DateTimeField("Дата создания", auto_now_add=True)
    status = models.CharField("Статус", max_length=20, choices=STATUS_CHOICES, default="new")
    preliminary_total = models.DecimalField("Предварительная сумма", max_digits=12, decimal_places=2, default=Decimal("0.00"))
    final_total = models.DecimalField("Итоговая сумма", max_digits=12, decimal_places=2, null=True, blank=True)

    class Meta:
        verbose_name = "Предзаказ"
        verbose_name_plural = "Предзаказы"
        ordering = ["-created_at"]
        constraints = [
            models.CheckConstraint(condition=Q(preliminary_total__gte=0), name="ck_preorder_preliminary_nonnegative"),
            models.CheckConstraint(condition=Q(final_total__isnull=True) | Q(final_total__gte=0), name="ck_preorder_final_nonnegative"),
        ]

    def __str__(self):
        return f"Предзаказ №{self.id}"

    def is_open(self):
        return timezone.now() < self.arrival_at - timedelta(hours=36)


class OrderItem(models.Model):
    order = models.ForeignKey(PreOrder, on_delete=models.CASCADE, related_name="items", verbose_name="Предзаказ")
    batch_product = models.ForeignKey(BatchProduct, on_delete=models.PROTECT, related_name="order_items", verbose_name="Продукт в партии")
    quantity = models.DecimalField("Заказанное количество или вес", max_digits=10, decimal_places=3)
    actual_quantity = models.DecimalField("Фактическое количество или вес", max_digits=10, decimal_places=3, null=True, blank=True)
    unit_price = models.DecimalField("Цена на момент заказа", max_digits=10, decimal_places=2)
    is_picked = models.BooleanField("Позиция собрана", default=False)

    class Meta:
        verbose_name = "Позиция предзаказа"
        verbose_name_plural = "Позиции предзаказов"
        ordering = ["order_id", "id"]
        constraints = [
            models.UniqueConstraint(fields=["order", "batch_product"], name="uq_order_batch_product"),
            models.CheckConstraint(condition=Q(quantity__gt=0), name="ck_order_item_quantity_positive"),
            models.CheckConstraint(condition=Q(unit_price__gte=0), name="ck_order_item_price_nonnegative"),
            models.CheckConstraint(
                condition=Q(actual_quantity__isnull=True) | (
                    Q(actual_quantity__gte=F("quantity") * Decimal("0.85")) &
                    Q(actual_quantity__lte=F("quantity") * Decimal("1.15"))
                ),
                name="ck_order_item_weight_range",
            ),
        ]

    def __str__(self):
        return f"Позиция №{self.id} в предзаказе №{self.order_id}"


class WeightAdjustment(models.Model):
    order_item = models.OneToOneField(OrderItem, on_delete=models.CASCADE, related_name="weight_adjustment", verbose_name="Позиция предзаказа")
    edited_by = models.ForeignKey(UserProfile, on_delete=models.PROTECT, related_name="weight_adjustments", verbose_name="Кто изменил")
    reason = models.CharField("Причина корректировки", max_length=255)
    changed_at = models.DateTimeField("Дата корректировки", auto_now_add=True)

    class Meta:
        verbose_name = "Корректировка веса"
        verbose_name_plural = "Корректировки веса"
        ordering = ["-changed_at"]

    def __str__(self):
        return f"Корректировка позиции №{self.order_item_id}"


class Delivery(models.Model):
    STATUS_CHOICES = [
        ("waiting", "Ожидает назначения"),
        ("assigned", "Курьер назначен"),
        ("in_transit", "В пути"),
        ("delivered", "Доставлена"),
        ("cancelled", "Отменена"),
    ]

    order = models.OneToOneField(PreOrder, on_delete=models.CASCADE, related_name="delivery", verbose_name="Предзаказ")
    courier = models.ForeignKey(UserProfile, on_delete=models.SET_NULL, related_name="deliveries", verbose_name="Курьер", null=True, blank=True)
    address = models.TextField("Адрес доставки")
    interval_start = models.DateTimeField("Начало интервала доставки")
    interval_end = models.DateTimeField("Конец интервала доставки")
    status = models.CharField("Статус доставки", max_length=15, choices=STATUS_CHOICES, default="waiting")
    delivered_at = models.DateTimeField("Время доставки", null=True, blank=True)

    class Meta:
        verbose_name = "Доставка"
        verbose_name_plural = "Доставки"
        ordering = ["interval_start"]
        constraints = [
            models.CheckConstraint(condition=Q(interval_end__gt=F("interval_start")), name="ck_delivery_interval")
        ]

    def __str__(self):
        return f"Доставка по предзаказу №{self.order_id}"