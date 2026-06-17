from codigo_candidato import calcular_media

def test_calculate_mean_with_empty_list():
    with pytest.raises(ZeroDivisionError):
        calcular_media([])