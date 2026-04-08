import django.db.models.deletion
from decimal import Decimal
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = []

    operations = [
        migrations.CreateModel(
            name='CodeSequence',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('prefix', models.CharField(max_length=50, unique=True, verbose_name='Prefixo')),
                ('last_value', models.PositiveIntegerField(default=0, verbose_name='Último valor')),
            ],
            options={
                'verbose_name': 'Sequência de Código',
                'verbose_name_plural': 'Sequências de Código',
                'db_table': 'crafting_code_sequence',
            },
        ),
        migrations.CreateModel(
            name='Recipe',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('code', models.SlugField(help_text='Identificador unico (ex: croissant-v1)', unique=True, verbose_name='Codigo')),
                ('name', models.CharField(max_length=200, verbose_name='Nome')),
                ('output_ref', models.CharField(help_text='Referencia do produto (ex: SKU, slug)', max_length=100, verbose_name='Produto de Saida')),
                ('batch_size', models.DecimalField(decimal_places=3, default=Decimal('1'), help_text='Unidades produzidas por batelada', max_digits=12, verbose_name='Tamanho do Lote')),
                ('steps', models.JSONField(blank=True, default=list, help_text="['Mistura', 'Modelagem', 'Forno']", verbose_name='Etapas')),
                ('is_active', models.BooleanField(default=True, verbose_name='Ativa')),
                ('meta', models.JSONField(blank=True, default=dict, verbose_name='Metadados')),
                ('created_at', models.DateTimeField(auto_now_add=True, verbose_name='Criado em')),
                ('updated_at', models.DateTimeField(auto_now=True, verbose_name='Atualizado em')),
            ],
            options={
                'verbose_name': 'Receita',
                'verbose_name_plural': 'Receitas',
                'db_table': 'crafting_recipe',
                'ordering': ['name'],
                'indexes': [models.Index(fields=['output_ref'], name='crafting_re_output__idx'), models.Index(fields=['is_active'], name='crafting_re_is_acti_idx')],
                'constraints': [models.CheckConstraint(condition=models.Q(('batch_size__gt', 0)), name='craft_recipe_batch_positive')],
            },
        ),
        migrations.CreateModel(
            name='WorkOrder',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('code', models.CharField(blank=True, max_length=20, unique=True, verbose_name='Codigo')),
                ('output_ref', models.CharField(help_text='Copiado da Recipe no plan', max_length=100, verbose_name='Produto')),
                ('quantity', models.DecimalField(decimal_places=3, help_text='Alvo atual (mutavel via adjust)', max_digits=12, verbose_name='Quantidade Alvo')),
                ('produced', models.DecimalField(blank=True, decimal_places=3, help_text='Set no close, imutavel depois', max_digits=12, null=True, verbose_name='Produzido')),
                ('status', models.CharField(choices=[('open', 'Aberta'), ('done', 'Concluida'), ('void', 'Cancelada')], default='open', max_length=10, verbose_name='Status')),
                ('rev', models.PositiveIntegerField(default=0, help_text='Optimistic concurrency counter', verbose_name='Revisao')),
                ('scheduled_date', models.DateField(blank=True, null=True, verbose_name='Data Agendada')),
                ('started_at', models.DateTimeField(blank=True, null=True, verbose_name='Iniciada em')),
                ('finished_at', models.DateTimeField(blank=True, null=True, verbose_name='Finalizada em')),
                ('source_ref', models.CharField(blank=True, help_text="'order:789', 'forecast:Q1'", max_length=100, verbose_name='Origem')),
                ('position_ref', models.CharField(blank=True, help_text="Ref da Position no Stocking (ex: 'producao')", max_length=100, verbose_name='Posição')),
                ('assigned_ref', models.CharField(blank=True, help_text="'user:joao'", max_length=100, verbose_name='Responsavel')),
                ('meta', models.JSONField(blank=True, default=dict, verbose_name='Metadados')),
                ('created_at', models.DateTimeField(auto_now_add=True, verbose_name='Criado em')),
                ('updated_at', models.DateTimeField(auto_now=True, verbose_name='Atualizado em')),
                ('recipe', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='work_orders', to='craftsman.recipe', verbose_name='Receita')),
            ],
            options={
                'verbose_name': 'Ordem de Producao',
                'verbose_name_plural': 'Ordens de Producao',
                'db_table': 'crafting_work_order',
                'ordering': ['-created_at'],
            },
        ),
        migrations.CreateModel(
            name='WorkOrderEvent',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('seq', models.PositiveIntegerField(verbose_name='Sequencia')),
                ('kind', models.CharField(choices=[('planned', 'Planejado'), ('adjusted', 'Ajustado'), ('closed', 'Encerrado'), ('voided', 'Cancelado')], max_length=20, verbose_name='Tipo')),
                ('payload', models.JSONField(blank=True, default=dict, verbose_name='Dados')),
                ('actor', models.CharField(blank=True, max_length=100, verbose_name='Ator')),
                ('idempotency_key', models.CharField(blank=True, max_length=200, null=True, unique=True, verbose_name='Chave de Idempotencia')),
                ('created_at', models.DateTimeField(auto_now_add=True, verbose_name='Criado em')),
                ('work_order', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='events', to='craftsman.workorder', verbose_name='Ordem')),
            ],
            options={
                'verbose_name': 'Evento da Ordem',
                'verbose_name_plural': 'Eventos da Ordem',
                'db_table': 'crafting_work_order_event',
                'ordering': ['work_order', 'seq'],
            },
        ),
        migrations.CreateModel(
            name='WorkOrderItem',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('kind', models.CharField(choices=[('requirement', 'Requisito'), ('consumption', 'Consumo'), ('output', 'Saida'), ('waste', 'Perda')], max_length=15, verbose_name='Tipo')),
                ('item_ref', models.CharField(help_text='SKU ou identificador do material', max_length=100, verbose_name='Referencia')),
                ('quantity', models.DecimalField(decimal_places=3, max_digits=12, verbose_name='Quantidade')),
                ('unit', models.CharField(blank=True, max_length=20, verbose_name='Unidade')),
                ('recorded_at', models.DateTimeField(verbose_name='Registrado em')),
                ('recorded_by', models.CharField(blank=True, max_length=100, verbose_name='Registrado por')),
                ('meta', models.JSONField(blank=True, default=dict, help_text='lot, expires, reason, step, etc.', verbose_name='Metadados')),
                ('work_order', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='items', to='craftsman.workorder', verbose_name='Ordem')),
            ],
            options={
                'verbose_name': 'Item da Ordem',
                'verbose_name_plural': 'Itens da Ordem',
                'db_table': 'crafting_work_order_item',
            },
        ),
        migrations.CreateModel(
            name='RecipeItem',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('input_ref', models.CharField(help_text='Referencia do material de entrada', max_length=100, verbose_name='Insumo')),
                ('quantity', models.DecimalField(decimal_places=3, help_text='Quantidade por batch_size', max_digits=12, verbose_name='Quantidade')),
                ('unit', models.CharField(default='kg', max_length=20, verbose_name='Unidade')),
                ('sort_order', models.PositiveSmallIntegerField(default=0, verbose_name='Ordem')),
                ('is_optional', models.BooleanField(default=False, help_text='Ingrediente alternativo', verbose_name='Opcional')),
                ('meta', models.JSONField(blank=True, default=dict, verbose_name='Metadados')),
                ('recipe', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='items', to='craftsman.recipe', verbose_name='Receita')),
            ],
            options={
                'verbose_name': 'Ingrediente',
                'verbose_name_plural': 'Ingredientes',
                'db_table': 'crafting_recipe_item',
                'ordering': ['sort_order'],
                'constraints': [models.CheckConstraint(condition=models.Q(('quantity__gt', 0)), name='craft_recipeitem_qty_positive')],
                'unique_together': {('recipe', 'input_ref')},
            },
        ),
        migrations.AddIndex(
            model_name='workorder',
            index=models.Index(fields=['status', 'scheduled_date'], name='crafting_wo_status_sched_idx'),
        ),
        migrations.AddIndex(
            model_name='workorder',
            index=models.Index(fields=['output_ref', 'status'], name='crafting_wo_output_status_idx'),
        ),
        migrations.AddIndex(
            model_name='workorder',
            index=models.Index(fields=['scheduled_date'], name='crafting_wo_sched_date_idx'),
        ),
        migrations.AddConstraint(
            model_name='workorder',
            constraint=models.CheckConstraint(condition=models.Q(('quantity__gt', 0)), name='craft_wo_quantity_positive'),
        ),
        migrations.AlterUniqueTogether(
            name='workorderevent',
            unique_together={('work_order', 'seq')},
        ),
        migrations.AddIndex(
            model_name='workorderitem',
            index=models.Index(fields=['work_order', 'kind'], name='crafting_wi_wo_kind_idx'),
        ),
        migrations.AddIndex(
            model_name='workorderitem',
            index=models.Index(fields=['item_ref', 'kind'], name='crafting_wi_item_kind_idx'),
        ),
        migrations.AddIndex(
            model_name='workorderitem',
            index=models.Index(fields=['recorded_at'], name='crafting_wi_recorded_idx'),
        ),
        migrations.AddConstraint(
            model_name='workorderitem',
            constraint=models.CheckConstraint(condition=models.Q(('quantity__gt', 0)), name='craft_woitem_qty_positive'),
        ),
    ]
