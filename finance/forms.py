from django import forms

from finance.models import CapitalLoan, CashVoucher, Invoice, PaymentExpenseMatch
from operations.models import TransactionCluster


class ClusterChoiceField(forms.ModelChoiceField):
    def label_from_instance(self, obj):
        vol = f"({obj.purchase_order.volume_mt} MT)" if hasattr(obj, "purchase_order") and obj.purchase_order else ""
        client_name = obj.client.name if obj.client else "Unknown Client"
        mill_name = obj.sugar_mill.name if obj.sugar_mill else "Unknown Mill"
        return f"{obj.reference_code} — {client_name} [{mill_name}] {vol}".strip()


class StandaloneInvoiceForm(forms.ModelForm):
    cluster = ClusterChoiceField(
        queryset=TransactionCluster.objects.none(),
        empty_label="-- Select Transaction Cluster --",
        widget=forms.Select(attrs={"class": "form-select-htc", "id": "id_standalone_cluster"}),
        label="Transaction Cluster",
    )

    class Meta:
        model = Invoice
        fields = ["cluster", "invoice_number", "amount", "issued_at", "status", "is_incremental", "incremental_percentage", "notes"]
        widgets = {
            "invoice_number": forms.TextInput(attrs={"class": "form-control-htc", "placeholder": "Auto-generated based on PO (e.g. SI-20260925-001)"}),
            "amount": forms.NumberInput(attrs={"class": "form-control-htc", "placeholder": "e.g. 1500000.00", "step": "0.01"}),
            "issued_at": forms.DateInput(attrs={"class": "form-control-htc", "type": "date"}),
            "status": forms.Select(attrs={"class": "form-select-htc"}),
            "is_incremental": forms.CheckboxInput(attrs={"class": "form-check-input", "id": "id_standalone_is_incremental"}),
            "incremental_percentage": forms.NumberInput(attrs={"class": "form-control-htc", "placeholder": "e.g. 50.00", "step": "0.01", "id": "id_standalone_incremental_pct"}),
            "notes": forms.TextInput(attrs={"class": "form-control-htc", "placeholder": "Optional invoice notes..."}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["invoice_number"].required = False
        self.fields["is_incremental"].required = False
        self.fields["incremental_percentage"].required = False
        self.fields["cluster"].queryset = (
            TransactionCluster.objects.filter(is_archived=False)
            .select_related("client", "sugar_mill", "purchase_order")
            .order_by("-created_at")
        )

    def clean_invoice_number(self):
        num = self.cleaned_data.get("invoice_number", "").strip()
        if not num:
            from operations.services.reference_generators import generate_si_reference
            cluster = self.cleaned_data.get("cluster")
            cluster_ref = cluster.reference_code if cluster else None
            num = generate_si_reference(cluster_ref)
        return num

    def clean(self):
        cleaned_data = super().clean()
        cluster = cleaned_data.get("cluster")
        is_incremental = cleaned_data.get("is_incremental")
        incremental_percentage = cleaned_data.get("incremental_percentage")

        if cluster:
            # 1. Check for Active Capital Loan Prerequisite
            if not cluster.loans.filter(status__in=["active", "pending_settlement", "closed"]).exists():
                self.add_error(
                    "cluster",
                    "A Capital Loan must be fulfilled (Active/Settled) for this transaction before invoices can be issued."
                )

            # 2. Check for Incremental Billing Requirement
            existing_qs = cluster.invoices.all()
            if self.instance and self.instance.pk:
                existing_qs = existing_qs.exclude(pk=self.instance.pk)
            if existing_qs.exists() and not is_incremental and not incremental_percentage:
                self.add_error(
                    "is_incremental",
                    "An invoice has already been issued for this transaction cluster. "
                    "Creation of additional invoices is restricted unless specified as an incremental billing (e.g. 50%, 25%). "
                    "Please check 'Incremental / Progress Billing' and specify the incremental percentage."
                )
        return cleaned_data


class InvoiceForm(forms.ModelForm):
    class Meta:
        model = Invoice
        fields = ["invoice_number", "amount", "issued_at", "status", "is_incremental", "incremental_percentage", "notes"]
        widgets = {
            "invoice_number": forms.TextInput(attrs={"class": "form-control-htc", "placeholder": "Auto-generated based on PO (e.g. SI-20260925-001)"}),
            "amount": forms.NumberInput(attrs={"class": "form-control-htc", "placeholder": "e.g. 1500000.00", "step": "0.01"}),
            "issued_at": forms.DateInput(attrs={"class": "form-control-htc", "type": "date"}),
            "status": forms.Select(attrs={"class": "form-select-htc"}),
            "is_incremental": forms.CheckboxInput(attrs={"class": "form-check-input", "id": "id_detail_is_incremental"}),
            "incremental_percentage": forms.NumberInput(attrs={"class": "form-control-htc", "placeholder": "e.g. 50.00", "step": "0.01", "id": "id_detail_incremental_pct"}),
            "notes": forms.TextInput(attrs={"class": "form-control-htc", "placeholder": "Optional invoice notes..."}),
        }

    def __init__(self, *args, cluster=None, **kwargs):
        self.cluster = cluster
        super().__init__(*args, **kwargs)
        self.fields["invoice_number"].required = False
        self.fields["is_incremental"].required = False
        self.fields["incremental_percentage"].required = False
        if self.cluster and not self.initial.get("invoice_number"):
            from operations.services.reference_generators import generate_si_reference
            self.initial["invoice_number"] = generate_si_reference(self.cluster.reference_code)
        if self.cluster and self.cluster.invoices.exists():
            self.initial["is_incremental"] = True

    def clean_invoice_number(self):
        num = self.cleaned_data.get("invoice_number", "").strip()
        if not num:
            from operations.services.reference_generators import generate_si_reference
            cluster_ref = self.cluster.reference_code if self.cluster else None
            num = generate_si_reference(cluster_ref)
        return num

    def clean(self):
        cleaned_data = super().clean()
        is_incremental = cleaned_data.get("is_incremental")
        incremental_percentage = cleaned_data.get("incremental_percentage")

        if self.cluster:
            # 1. Check for Active Capital Loan Prerequisite
            if not self.cluster.loans.filter(status__in=["active", "pending_settlement", "closed"]).exists():
                raise forms.ValidationError(
                    "A Capital Loan must be fulfilled (Active/Settled) for this transaction before invoices can be issued."
                )

            # 2. Check for Incremental Billing Requirement
            existing_qs = self.cluster.invoices.all()
            if self.instance and self.instance.pk:
                existing_qs = existing_qs.exclude(pk=self.instance.pk)
            if existing_qs.exists() and not is_incremental and not incremental_percentage:
                self.add_error(
                    "is_incremental",
                    "An invoice has already been issued for this transaction cluster. "
                    "Creation of additional invoices is restricted unless specified as an incremental billing (e.g. 50%, 25%). "
                    "Please check 'Incremental / Progress Billing' and specify the incremental percentage."
                )
        return cleaned_data


class CashVoucherForm(forms.ModelForm):
    class Meta:
        model = CashVoucher
        fields = ["voucher_number", "amount", "purpose", "cheque_number", "cheque_date", "issued_at"]
        widgets = {
            "voucher_number": forms.TextInput(attrs={"class": "form-control-htc", "placeholder": "Auto-generated based on PO (e.g. CV-20260925-001)"}),
            "amount": forms.NumberInput(attrs={"class": "form-control-htc", "placeholder": "e.g. 25000.00", "step": "0.01"}),
            "purpose": forms.TextInput(attrs={"class": "form-control-htc", "placeholder": "e.g. Barging & Pier Fees"}),
            "cheque_number": forms.TextInput(attrs={"class": "form-control-htc", "placeholder": "e.g. CHQ-8849201"}),
            "cheque_date": forms.DateInput(attrs={"class": "form-control-htc", "type": "date"}),
            "issued_at": forms.DateInput(attrs={"class": "form-control-htc", "type": "date"}),
        }

    def __init__(self, *args, cluster=None, **kwargs):
        self.cluster = cluster
        super().__init__(*args, **kwargs)
        self.fields["voucher_number"].required = False
        if self.cluster and not self.initial.get("voucher_number"):
            from operations.services.reference_generators import generate_cv_reference
            self.initial["voucher_number"] = generate_cv_reference(self.cluster.reference_code)

    def clean_voucher_number(self):
        num = self.cleaned_data.get("voucher_number", "").strip()
        if not num:
            from operations.services.reference_generators import generate_cv_reference
            cluster_ref = self.cluster.reference_code if self.cluster else None
            num = generate_cv_reference(cluster_ref)
        return num


class StandaloneLoanForm(forms.ModelForm):
    cluster = ClusterChoiceField(
        queryset=TransactionCluster.objects.none(),
        empty_label="-- Select Target Transaction Cluster --",
        widget=forms.Select(attrs={"class": "form-select-htc", "id": "id_standalone_loan_cluster"}),
        label="Linked Transaction Cluster",
    )

    class Meta:
        model = CapitalLoan
        fields = [
            "cluster",
            "bank_name",
            "principal",
            "interest_rate_annual",
            "start_date",
            "due_date",
            "cheque_number",
            "cheque_date",
            "bank_account_number",
            "logistics_deposit_percentage",
            "status",
        ]
        widgets = {
            "bank_name": forms.TextInput(attrs={"class": "form-control-htc", "placeholder": "e.g. BDO Unibank / Metropolitan Bank"}),
            "principal": forms.NumberInput(attrs={"class": "form-control-htc", "placeholder": "e.g. 5000000.00", "step": "0.01"}),
            "interest_rate_annual": forms.NumberInput(attrs={"class": "form-control-htc", "placeholder": "e.g. 12.0000", "step": "0.0001"}),
            "start_date": forms.DateInput(attrs={"class": "form-control-htc", "type": "date"}),
            "due_date": forms.DateInput(attrs={"class": "form-control-htc", "type": "date"}),
            "cheque_number": forms.TextInput(attrs={"class": "form-control-htc", "placeholder": "e.g. CHQ-990142"}),
            "cheque_date": forms.DateInput(attrs={"class": "form-control-htc", "type": "date"}),
            "bank_account_number": forms.TextInput(attrs={"class": "form-control-htc", "placeholder": "e.g. 0048-2910-44"}),
            "logistics_deposit_percentage": forms.NumberInput(attrs={"class": "form-control-htc", "placeholder": "50.00", "step": "0.01"}),
            "status": forms.Select(attrs={"class": "form-select-htc"}),
        }

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["cluster"].queryset = (
            TransactionCluster.objects.filter(is_archived=False)
            .select_related("client", "sugar_mill", "purchase_order")
            .order_by("-created_at")
        )
        self.fields["cheque_number"].required = False
        self.fields["cheque_date"].required = False
        self.fields["bank_account_number"].required = False
        self.fields["logistics_deposit_percentage"].required = False

        from accounts.permissions import user_has_perm
        can_verify = user and user_has_perm(user, "verify_loan")

        if can_verify:
            self.fields["status"].choices = [
                (CapitalLoan.Status.PENDING_CREATION, "Pending Creation Approval (Default)"),
                (CapitalLoan.Status.ACTIVE, "Active Facility (Pre-Approved / Approved Immediately)"),
            ]
            self.fields["status"].initial = CapitalLoan.Status.PENDING_CREATION
        else:
            self.fields["status"].choices = [
                (CapitalLoan.Status.PENDING_CREATION, "Pending Creation Approval"),
            ]
            self.fields["status"].initial = CapitalLoan.Status.PENDING_CREATION
            self.fields["status"].disabled = True
            self.fields["status"].required = False

    def clean(self):
        cleaned_data = super().clean()
        principal = cleaned_data.get("principal")
        interest_rate = cleaned_data.get("interest_rate_annual")
        start_date = cleaned_data.get("start_date")
        due_date = cleaned_data.get("due_date")

        if principal is not None and principal <= 0:
            self.add_error("principal", "Loan principal amount must be a positive number greater than ₱0.00.")

        if interest_rate is not None and interest_rate < 0:
            self.add_error("interest_rate_annual", "Annual interest rate cannot be negative.")

        if start_date and due_date and due_date <= start_date:
            self.add_error("due_date", "Facility due date must be later than the loan start date.")

        return cleaned_data


class CapitalLoanForm(forms.ModelForm):
    class Meta:
        model = CapitalLoan
        fields = [
            "bank_name",
            "principal",
            "interest_rate_annual",
            "start_date",
            "due_date",
            "cheque_number",
            "cheque_date",
            "bank_account_number",
            "logistics_deposit_percentage",
            "status",
        ]
        widgets = {
            "bank_name": forms.TextInput(attrs={"class": "form-control-htc", "placeholder": "e.g. BDO Unibank"}),
            "principal": forms.NumberInput(attrs={"class": "form-control-htc", "placeholder": "e.g. 5000000.00", "step": "0.01"}),
            "interest_rate_annual": forms.NumberInput(attrs={"class": "form-control-htc", "placeholder": "e.g. 12.0000", "step": "0.0001"}),
            "start_date": forms.DateInput(attrs={"class": "form-control-htc", "type": "date"}),
            "due_date": forms.DateInput(attrs={"class": "form-control-htc", "type": "date"}),
            "cheque_number": forms.TextInput(attrs={"class": "form-control-htc", "placeholder": "e.g. CHQ-990142"}),
            "cheque_date": forms.DateInput(attrs={"class": "form-control-htc", "type": "date"}),
            "bank_account_number": forms.TextInput(attrs={"class": "form-control-htc", "placeholder": "e.g. 0048-2910-44"}),
            "logistics_deposit_percentage": forms.NumberInput(attrs={"class": "form-control-htc", "placeholder": "50.00", "step": "0.01"}),
            "status": forms.Select(attrs={"class": "form-select-htc"}),
        }

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["cheque_number"].required = False
        self.fields["cheque_date"].required = False
        self.fields["bank_account_number"].required = False
        self.fields["logistics_deposit_percentage"].required = False

        # Restrict status choices on loan addition:
        # Default is PENDING_CREATION.
        # Only Admins and Ops Managers can select between Pending Creation and Active Facility (pre-approved).
        from accounts.permissions import user_has_perm
        can_verify = user and user_has_perm(user, "verify_loan")

        if can_verify:
            self.fields["status"].choices = [
                (CapitalLoan.Status.PENDING_CREATION, "Pending Creation Approval (Default)"),
                (CapitalLoan.Status.ACTIVE, "Active Facility (Pre-Approved / Existing)"),
            ]
            self.fields["status"].initial = CapitalLoan.Status.PENDING_CREATION
        else:
            self.fields["status"].choices = [
                (CapitalLoan.Status.PENDING_CREATION, "Pending Creation Approval"),
            ]
            self.fields["status"].initial = CapitalLoan.Status.PENDING_CREATION
            self.fields["status"].disabled = True
            self.fields["status"].required = False

    def clean(self):
        cleaned_data = super().clean()
        principal = cleaned_data.get("principal")
        interest_rate = cleaned_data.get("interest_rate_annual")
        start_date = cleaned_data.get("start_date")
        due_date = cleaned_data.get("due_date")

        if principal is not None and principal <= 0:
            self.add_error("principal", "Loan principal amount must be a positive number greater than ₱0.00.")

        if interest_rate is not None and interest_rate < 0:
            self.add_error("interest_rate_annual", "Annual interest rate cannot be negative.")

        if start_date and due_date and due_date <= start_date:
            self.add_error("due_date", "Facility due date must be later than the loan start date.")

        return cleaned_data


class PaymentExpenseMatchForm(forms.ModelForm):
    class Meta:
        model = PaymentExpenseMatch
        fields = ["payment_reference", "expense_type", "amount", "notes"]
        labels = {
            "payment_reference": "Step 1: Bank Deposit / Receipt / Voucher Ref #",
            "expense_type": "Step 2: Matching Allocation Category",
            "amount": "Step 3: Allocated Amount (₱)",
            "notes": "Reconciliation Notes / Discrepancy Explanation",
        }
        widgets = {
            "payment_reference": forms.TextInput(attrs={"class": "form-control-htc", "placeholder": "e.g. OR-99482 / DEP-20260828-01"}),
            "expense_type": forms.Select(attrs={"class": "form-select-htc"}),
            "amount": forms.NumberInput(attrs={"class": "form-control-htc", "placeholder": "e.g. 500000.00", "step": "0.01"}),
            "notes": forms.TextInput(attrs={"class": "form-control-htc", "placeholder": "Optional reconciliation notes..."}),
        }
