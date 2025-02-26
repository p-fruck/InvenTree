"""JSON serializers for Company app."""

import io

from django.core.files.base import ContentFile
from django.utils.translation import gettext_lazy as _

from rest_framework import serializers
from sql_util.utils import SubqueryCount

import part.filters
from common.settings import currency_code_default, currency_code_mappings
from InvenTree.serializers import (InvenTreeAttachmentSerializer,
                                   InvenTreeDecimalField,
                                   InvenTreeImageSerializerField,
                                   InvenTreeModelSerializer,
                                   InvenTreeMoneySerializer, RemoteImageMixin)
from part.serializers import PartBriefSerializer

from .models import (Company, CompanyAttachment, ManufacturerPart,
                     ManufacturerPartAttachment, ManufacturerPartParameter,
                     SupplierPart, SupplierPriceBreak)


class CompanyBriefSerializer(InvenTreeModelSerializer):
    """Serializer for Company object (limited detail)"""

    url = serializers.CharField(source='get_absolute_url', read_only=True)

    image = serializers.CharField(source='get_thumbnail_url', read_only=True)

    class Meta:
        """Metaclass options."""

        model = Company
        fields = [
            'pk',
            'url',
            'name',
            'description',
            'image',
        ]


class CompanySerializer(RemoteImageMixin, InvenTreeModelSerializer):
    """Serializer for Company object (full detail)"""

    @staticmethod
    def annotate_queryset(queryset):
        """Annoate the supplied queryset with aggregated information"""
        # Add count of parts manufactured
        queryset = queryset.annotate(
            parts_manufactured=SubqueryCount('manufactured_parts')
        )

        queryset = queryset.annotate(
            parts_supplied=SubqueryCount('supplied_parts')
        )

        return queryset

    url = serializers.CharField(source='get_absolute_url', read_only=True)

    image = InvenTreeImageSerializerField(required=False, allow_null=True)

    parts_supplied = serializers.IntegerField(read_only=True)
    parts_manufactured = serializers.IntegerField(read_only=True)

    currency = serializers.ChoiceField(
        choices=currency_code_mappings(),
        initial=currency_code_default,
        help_text=_('Default currency used for this supplier'),
        label=_('Currency Code'),
        required=True,
    )

    class Meta:
        """Metaclass options."""

        model = Company
        fields = [
            'pk',
            'url',
            'name',
            'description',
            'website',
            'name',
            'phone',
            'address',
            'email',
            'currency',
            'contact',
            'link',
            'image',
            'is_customer',
            'is_manufacturer',
            'is_supplier',
            'notes',
            'parts_supplied',
            'parts_manufactured',
            'remote_image',
        ]

    def save(self):
        """Save the Company instance"""
        super().save()

        company = self.instance

        # Check if an image was downloaded from a remote URL
        remote_img = getattr(self, 'remote_image_file', None)

        if remote_img and company:
            fmt = remote_img.format or 'PNG'
            buffer = io.BytesIO()
            remote_img.save(buffer, format=fmt)

            # Construct a simplified name for the image
            filename = f"company_{company.pk}_image.{fmt.lower()}"

            company.image.save(
                filename,
                ContentFile(buffer.getvalue()),
            )

        return self.instance


class CompanyAttachmentSerializer(InvenTreeAttachmentSerializer):
    """Serializer for the CompanyAttachment class"""

    class Meta:
        """Metaclass defines serializer options"""
        model = CompanyAttachment

        fields = InvenTreeAttachmentSerializer.attachment_fields([
            'company',
        ])


class ManufacturerPartSerializer(InvenTreeModelSerializer):
    """Serializer for ManufacturerPart object."""

    part_detail = PartBriefSerializer(source='part', many=False, read_only=True)

    manufacturer_detail = CompanyBriefSerializer(source='manufacturer', many=False, read_only=True)

    pretty_name = serializers.CharField(read_only=True)

    def __init__(self, *args, **kwargs):
        """Initialize this serializer with extra detail fields as required"""
        part_detail = kwargs.pop('part_detail', True)
        manufacturer_detail = kwargs.pop('manufacturer_detail', True)
        prettify = kwargs.pop('pretty', False)

        super().__init__(*args, **kwargs)

        if part_detail is not True:
            self.fields.pop('part_detail')

        if manufacturer_detail is not True:
            self.fields.pop('manufacturer_detail')

        if prettify is not True:
            self.fields.pop('pretty_name')

    manufacturer = serializers.PrimaryKeyRelatedField(queryset=Company.objects.filter(is_manufacturer=True))

    class Meta:
        """Metaclass options."""

        model = ManufacturerPart
        fields = [
            'pk',
            'part',
            'part_detail',
            'pretty_name',
            'manufacturer',
            'manufacturer_detail',
            'description',
            'MPN',
            'link',
        ]


class ManufacturerPartAttachmentSerializer(InvenTreeAttachmentSerializer):
    """Serializer for the ManufacturerPartAttachment class."""

    class Meta:
        """Metaclass options."""

        model = ManufacturerPartAttachment

        fields = InvenTreeAttachmentSerializer.attachment_fields([
            'manufacturer_part',
        ])


class ManufacturerPartParameterSerializer(InvenTreeModelSerializer):
    """Serializer for the ManufacturerPartParameter model."""

    manufacturer_part_detail = ManufacturerPartSerializer(source='manufacturer_part', many=False, read_only=True)

    def __init__(self, *args, **kwargs):
        """Initialize this serializer with extra detail fields as required"""
        man_detail = kwargs.pop('manufacturer_part_detail', False)

        super().__init__(*args, **kwargs)

        if not man_detail:
            self.fields.pop('manufacturer_part_detail')

    class Meta:
        """Metaclass options."""

        model = ManufacturerPartParameter

        fields = [
            'pk',
            'manufacturer_part',
            'manufacturer_part_detail',
            'name',
            'value',
            'units',
        ]


class SupplierPartSerializer(InvenTreeModelSerializer):
    """Serializer for SupplierPart object."""

    # Annotated field showing total in-stock quantity
    in_stock = serializers.FloatField(read_only=True)

    part_detail = PartBriefSerializer(source='part', many=False, read_only=True)

    supplier_detail = CompanyBriefSerializer(source='supplier', many=False, read_only=True)

    manufacturer_detail = CompanyBriefSerializer(source='manufacturer_part.manufacturer', many=False, read_only=True)

    pretty_name = serializers.CharField(read_only=True)

    pack_size = serializers.FloatField(label=_('Pack Quantity'))

    def __init__(self, *args, **kwargs):
        """Initialize this serializer with extra detail fields as required"""

        # Check if 'available' quantity was supplied
        self.has_available_quantity = 'available' in kwargs.get('data', {})

        brief = kwargs.pop('brief', False)

        detail_default = not brief

        part_detail = kwargs.pop('part_detail', detail_default)
        supplier_detail = kwargs.pop('supplier_detail', detail_default)
        manufacturer_detail = kwargs.pop('manufacturer_detail', detail_default)

        prettify = kwargs.pop('pretty', False)

        super().__init__(*args, **kwargs)

        if part_detail is not True:
            self.fields.pop('part_detail')

        if supplier_detail is not True:
            self.fields.pop('supplier_detail')

        if manufacturer_detail is not True:
            self.fields.pop('manufacturer_detail')
            self.fields.pop('manufacturer_part_detail')

        if prettify is not True:
            self.fields.pop('pretty_name')

    supplier = serializers.PrimaryKeyRelatedField(queryset=Company.objects.filter(is_supplier=True))

    manufacturer = serializers.CharField(read_only=True)

    MPN = serializers.CharField(read_only=True)

    manufacturer_part_detail = ManufacturerPartSerializer(source='manufacturer_part', read_only=True)

    url = serializers.CharField(source='get_absolute_url', read_only=True)

    # Date fields
    updated = serializers.DateTimeField(allow_null=True, read_only=True)

    class Meta:
        """Metaclass options."""

        model = SupplierPart
        fields = [
            'available',
            'availability_updated',
            'description',
            'in_stock',
            'link',
            'manufacturer',
            'manufacturer_detail',
            'manufacturer_part',
            'manufacturer_part_detail',
            'MPN',
            'note',
            'pk',
            'barcode_hash',
            'packaging',
            'pack_size',
            'part',
            'part_detail',
            'pretty_name',
            'SKU',
            'supplier',
            'supplier_detail',
            'url',
            'updated',
        ]

        read_only_fields = [
            'availability_updated',
            'barcode_hash',
        ]

    @staticmethod
    def annotate_queryset(queryset):
        """Annotate the SupplierPart queryset with extra fields:

        Fields:
            in_stock: Current stock quantity for each SupplierPart
        """

        queryset = queryset.annotate(
            in_stock=part.filters.annotate_total_stock()
        )

        return queryset

    def update(self, supplier_part, data):
        """Custom update functionality for the serializer"""

        available = data.pop('available', None)

        response = super().update(supplier_part, data)

        if available is not None and self.has_available_quantity:
            supplier_part.update_available_quantity(available)

        return response

    def create(self, validated_data):
        """Extract manufacturer data and process ManufacturerPart."""

        # Extract 'available' quantity from the serializer
        available = validated_data.pop('available', None)

        # Create SupplierPart
        supplier_part = super().create(validated_data)

        if available is not None and self.has_available_quantity:
            supplier_part.update_available_quantity(available)

        # Get ManufacturerPart raw data (unvalidated)
        manufacturer = self.initial_data.get('manufacturer', None)
        MPN = self.initial_data.get('MPN', None)

        if manufacturer and MPN:
            kwargs = {
                'manufacturer': manufacturer,
                'MPN': MPN,
            }
            supplier_part.save(**kwargs)

        return supplier_part


class SupplierPriceBreakSerializer(InvenTreeModelSerializer):
    """Serializer for SupplierPriceBreak object."""

    def __init__(self, *args, **kwargs):
        """Initialize this serializer with extra fields as required"""

        supplier_detail = kwargs.pop('supplier_detail', False)
        part_detail = kwargs.pop('part_detail', False)

        super().__init__(*args, **kwargs)

        if not supplier_detail:
            self.fields.pop('supplier_detail')

        if not part_detail:
            self.fields.pop('part_detail')

    quantity = InvenTreeDecimalField()

    price = InvenTreeMoneySerializer(
        allow_null=True,
        required=True,
        label=_('Price'),
    )

    price_currency = serializers.ChoiceField(
        choices=currency_code_mappings(),
        default=currency_code_default,
        label=_('Currency'),
    )

    supplier = serializers.PrimaryKeyRelatedField(source='part.supplier', many=False, read_only=True)

    supplier_detail = CompanyBriefSerializer(source='part.supplier', many=False, read_only=True)

    # Detail serializer for SupplierPart
    part_detail = SupplierPartSerializer(source='part', brief=True, many=False, read_only=True)

    class Meta:
        """Metaclass options."""

        model = SupplierPriceBreak
        fields = [
            'pk',
            'part',
            'part_detail',
            'quantity',
            'price',
            'price_currency',
            'supplier',
            'supplier_detail',
            'updated',
        ]
