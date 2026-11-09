import unittest
from unittest.mock import MagicMock, patch
from etg_moteur import nextwise, stockage, service_portefeuille as sp


class TestNextwise(unittest.TestCase):
    def test_nettoyer_nombre(self):
        self.assertEqual(nextwise.nettoyer_nombre("12 221,20 €"), 12221.20)
        self.assertEqual(nextwise.nettoyer_nombre("200 000,00 €"), 200000.0)
        self.assertEqual(nextwise.nettoyer_nombre("-0,37%"), -0.37)
        self.assertEqual(nextwise.nettoyer_nombre(None), 0.0)
        self.assertEqual(nextwise.nettoyer_nombre(""), 0.0)

    @patch("etg_moteur.nextwise.recuperer_donnees")
    def test_synchroniser_succes(self, mock_recup):
        mock_recup.return_value = {
            "nom_club": "Mon club test",
            "cash": 12221.20,
            "valeur_totale": 199266.46,
            "performance": "-0,37%",
            "positions": [
                {"ticker": "AEEM", "cntShares": 1222},
                {"ticker": "500", "cntShares": 66},
            ]
        }
        st = stockage.StockageLocal("/tmp/test_etg_st_nw")
        res = nextwise.synchroniser(st=st, email="test@example.com", password="pwd", pf_id="123")
        self.assertTrue(res["ok"])
        self.assertEqual(res["cash"], 12221.20)
        self.assertEqual(res["quantites"]["AEEM"], 1222)
        self.assertEqual(res["quantites"]["500"], 66)

        lu = sp.lire_positions(st)
        self.assertIsNotNone(lu)
        saisie, _ = lu
        self.assertEqual(saisie["cash"], 12221.20)
