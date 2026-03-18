# This is an auto-generated Django model module.
# You'll have to do the following manually to clean this up:
#   * Rearrange models' order
#   * Make sure each model has one field with primary_key=True
#   * Make sure each ForeignKey and OneToOneField has `on_delete` set to the desired behavior
#   * Remove `managed = True` lines if you wish to allow Django to create, modify, and delete the table
# Feel free to rename the models, but don't rename db_table values or field names.
from django.db import models


class Busena(models.Model):
    id = models.IntegerField(db_column='Id', primary_key=True)   
    name = models.CharField(db_column='Name', max_length=50)   

    class Meta:
        managed = True
        db_table = 'Busena'
        verbose_name_plural = "Būsenos"


class Mokejimas(models.Model):
    id = models.AutoField(db_column='Id', primary_key=True)   
    atlikimo_data = models.DateField(db_column='Atlikimo_data')   
    sumoketa_suma = models.DecimalField(db_column='Sumoketa_suma', max_digits=10, decimal_places=2)   
    fk_statusas = models.ForeignKey('Statusas', models.DO_NOTHING, db_column='fk_Statusas')   
    fk_prenumerata = models.ForeignKey('Prenumerata', models.DO_NOTHING, db_column='fk_Prenumerata')   
    fk_paslauga = models.ForeignKey('TeikiamaPaslauga', models.DO_NOTHING, db_column='fk_Paslauga')   

    class Meta:
        managed = True
        db_table = 'Mokejimas'
        verbose_name_plural = "Mokėjimai"


class Naudotojas(models.Model):
    id = models.AutoField(db_column='Id', primary_key=True)   
    vardas = models.CharField(db_column='Vardas', max_length=255)   
    pavarde = models.CharField(db_column='Pavarde', max_length=255)   
    el_pastas = models.CharField(db_column='El_pastas', unique=True, max_length=255)   
    fk_prisijungimas = models.OneToOneField('Prisijungimas', models.DO_NOTHING, db_column='fk_Prisijungimas')   

    class Meta:
        managed = True
        db_table = 'Naudotojas'
        verbose_name_plural = "Naudotojai"


class Prenumerata(models.Model):
    id = models.AutoField(db_column='Id', primary_key=True)   
    pradzios_laikas = models.DateField(db_column='Pradzios_laikas')   
    atnaujinimo_laikas = models.DateField(db_column='Atnaujinimo_laikas')   
    atliktos_uzklausos = models.IntegerField(db_column='Atliktos_uzklausos')   
    fk_busena = models.ForeignKey(Busena, models.DO_NOTHING, db_column='fk_Busena')   
    fk_naudotojas = models.ForeignKey(Naudotojas, models.DO_NOTHING, db_column='fk_Naudotojas')   

    class Meta:
        managed = True
        db_table = 'Prenumerata'
        verbose_name_plural = "Prenumeratos"


class Prisijungimas(models.Model):
    el_pastas = models.CharField(db_column='El_pastas', primary_key=True, max_length=255)   
    slaptazodis = models.CharField(db_column='Slaptazodis', max_length=255)   

    class Meta:
        managed = True
        db_table = 'Prisijungimas'
        verbose_name_plural = "Prisijungimai"


class Statusas(models.Model):
    id = models.IntegerField(db_column='Id', primary_key=True)   
    name = models.CharField(db_column='Name', max_length=50)   

    class Meta:
        managed = True
        db_table = 'Statusas'
        verbose_name_plural = "Statusai"


class Svecias(models.Model):
    id = models.AutoField(db_column='Id', primary_key=True)   
    ip_adresas = models.CharField(db_column='Ip_adresas', unique=True, max_length=255)   
    uzklausu_skaicius = models.IntegerField(db_column='Uzklausu_skaicius')   

    class Meta:
        managed = True
        db_table = 'Svecias'
        verbose_name_plural = "Svečiai"



class TeikiamaPaslauga(models.Model):
    id = models.AutoField(db_column='Id', primary_key=True)   
    pavadinimas = models.CharField(db_column='Pavadinimas', max_length=255)   
    kaina = models.DecimalField(db_column='Kaina', max_digits=10, decimal_places=2)   
    trukme = models.IntegerField(db_column='Trukme')   
    uzklausu_limitas = models.IntegerField(db_column='Uzklausu_limitas')   
    fk_prenumerata = models.OneToOneField(Prenumerata, models.DO_NOTHING, db_column='fk_Prenumerata')   

    class Meta:
        managed = True
        db_table = 'Teikiama_paslauga'
        verbose_name_plural = "Teikiamos paslaugos"


class Uzklausa(models.Model):
    id = models.AutoField(db_column='Id', primary_key=True)   
    uzklausos_data = models.DateField(db_column='Uzklausos_data')   
    uzklausa_text = models.CharField(db_column='Uzklausa_text', max_length=255)   
    atsakymas = models.CharField(db_column='Atsakymas', max_length=255, blank=True, null=True)   
    fk_naudotojas = models.ForeignKey(Naudotojas, models.DO_NOTHING, db_column='fk_Naudotojas')   

    class Meta:
        managed = True
        db_table = 'Uzklausa'
        verbose_name_plural = "Užklausos"
