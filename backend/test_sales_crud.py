import unittest
import uuid
import re

from fastapi.testclient import TestClient

from backend.main import app


class SalesCrudTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def _login(self, email: str, password: str = 'password123') -> str:
        response = self.client.post('/auth/login', json={'email': email, 'password': password})
        self.assertEqual(response.status_code, 200)
        return response.json()['access_token']

    def _create_category(self, token: str, name: str) -> int:
        response = self.client.post(
            '/categories',
            headers={'Authorization': f'Bearer {token}'},
            json={'name': name, 'description': 'Sales test category', 'status': 'active'},
        )
        self.assertEqual(response.status_code, 200)
        return response.json()['id']

    def _create_product(self, token: str, category_id: int, sku: str, stock: int = 20) -> int:
        response = self.client.post(
            '/products',
            headers={'Authorization': f'Bearer {token}'},
            json={
                'name': f'Product {sku}',
                'sku': sku,
                'categoryId': category_id,
                'brand': 'RetailPulse',
                'description': 'Sales test product',
                'unitPrice': 15.0,
                'costPrice': 10.0,
                'initialStockQuantity': stock,
                'unitOfMeasure': 'pcs',
                'status': 'active',
            },
        )
        self.assertEqual(response.status_code, 200)
        return response.json()['id']

    def test_sales_crud_and_analyst_access(self):
        admin_token = self._login('admin@retailpulse.com')
        analyst_token = self._login('analyst@retailpulse.com')

        suffix = uuid.uuid4().hex[:6]
        category_id = self._create_category(admin_token, f'Sales {suffix}')
        product_id = self._create_product(admin_token, category_id, f'SALE-{suffix}', stock=20)

        selectable = self.client.get('/sales/products/selectable', headers={'Authorization': f'Bearer {analyst_token}'})
        self.assertEqual(selectable.status_code, 200)
        selectable_body = selectable.json()
        self.assertTrue(any(item['id'] == product_id and item['categoryName'] for item in selectable_body))

        created = self.client.post(
            '/sales/transactions',
            headers={'Authorization': f'Bearer {analyst_token}'},
            json={
                'productId': product_id,
                'quantity': 3,
                'unitPrice': 15.0,
                'customerName': 'ACME Retail',
                'saleDateTime': '2026-07-17T10:00:00',
                'salesChannel': 'In-Store',
                'paymentMethod': 'Cash',
                'discountAmount': 5,
                'taxAmount': 2,
            },
        )
        self.assertEqual(created.status_code, 200)
        created_body = created.json()
        self.assertRegex(created_body['invoiceNumber'], r'^INV-\d{4}-\d{6}$')
        transaction_id = created_body['transactionId']
        self.assertEqual(created_body['lines'][0]['productId'], product_id)
        self.assertEqual(created_body['lines'][0]['categoryId'], category_id)
        self.assertEqual(created_body['lines'][0]['remainingStock'], 17)

        created_second = self.client.post(
            '/sales/transactions',
            headers={'Authorization': f'Bearer {analyst_token}'},
            json={
                'productId': product_id,
                'quantity': 1,
                'unitPrice': 15.0,
                'customerName': 'Second Customer',
                'saleDateTime': '2026-07-17T10:30:00',
                'salesChannel': 'Online',
                'paymentMethod': 'Card',
                'discountAmount': 0,
                'taxAmount': 0,
            },
        )
        self.assertEqual(created_second.status_code, 200)
        second_invoice = created_second.json()['invoiceNumber']
        self.assertRegex(second_invoice, r'^INV-\d{4}-\d{6}$')
        self.assertNotEqual(created_body['invoiceNumber'], second_invoice)
        self.assertEqual(created_second.json()['lines'][0]['remainingStock'], 16)

        product_after_create = self.client.get(
            f'/products/{product_id}',
            headers={'Authorization': f'Bearer {admin_token}'},
        )
        self.assertEqual(product_after_create.status_code, 200)
        self.assertEqual(product_after_create.json()['stockQuantity'], 16)

        listing = self.client.get('/sales/transactions', headers={'Authorization': f'Bearer {analyst_token}'})
        self.assertEqual(listing.status_code, 200)
        self.assertTrue(any(item['transactionId'] == transaction_id for item in listing.json()))

        updated = self.client.put(
            f'/sales/transactions/{transaction_id}',
            headers={'Authorization': f'Bearer {analyst_token}'},
            json={
                'productId': product_id,
                'quantity': 4,
                'unitPrice': 15.0,
                'customerName': 'ACME Retail Updated',
                'saleDateTime': '2026-07-17T11:00:00',
                'salesChannel': 'Online',
                'paymentMethod': 'Card',
                'discountAmount': 4,
                'taxAmount': 3,
            },
        )
        self.assertEqual(updated.status_code, 200)
        updated_body = updated.json()
        self.assertEqual(updated_body['customerName'], 'ACME Retail Updated')
        self.assertEqual(updated_body['lines'][0]['quantity'], 4)
        self.assertEqual(updated_body['lines'][0]['remainingStock'], 15)

        product_after_update = self.client.get(
            f'/products/{product_id}',
            headers={'Authorization': f'Bearer {admin_token}'},
        )
        self.assertEqual(product_after_update.status_code, 200)
        self.assertEqual(product_after_update.json()['stockQuantity'], 15)

        details = self.client.get(
            f'/sales/transactions/{transaction_id}',
            headers={'Authorization': f'Bearer {analyst_token}'},
        )
        self.assertEqual(details.status_code, 200)
        self.assertEqual(details.json()['transactionId'], transaction_id)

        deleted = self.client.delete(
            f'/sales/transactions/{transaction_id}',
            headers={'Authorization': f'Bearer {analyst_token}'},
        )
        self.assertEqual(deleted.status_code, 200)

        product_after_delete = self.client.get(
            f'/products/{product_id}',
            headers={'Authorization': f'Bearer {admin_token}'},
        )
        self.assertEqual(product_after_delete.status_code, 200)
        self.assertEqual(product_after_delete.json()['stockQuantity'], 19)

    def test_zero_stock_marks_product_out_of_stock_and_blocks_follow_up_sales(self):
        admin_token = self._login('admin@retailpulse.com')
        analyst_token = self._login('analyst@retailpulse.com')

        suffix = uuid.uuid4().hex[:6]
        category_id = self._create_category(admin_token, f'Zero Stock {suffix}')
        product_id = self._create_product(admin_token, category_id, f'ZERO-{suffix}', stock=1)

        created = self.client.post(
            '/sales/transactions',
            headers={'Authorization': f'Bearer {analyst_token}'},
            json={
                'productId': product_id,
                'quantity': 1,
                'unitPrice': 15.0,
                'customerName': 'Final Buyer',
                'saleDateTime': '2026-07-17T12:00:00',
                'salesChannel': 'In-Store',
                'paymentMethod': 'Cash',
                'discountAmount': 0,
                'taxAmount': 0,
            },
        )
        self.assertEqual(created.status_code, 200)
        self.assertEqual(created.json()['lines'][0]['remainingStock'], 0)

        product_after_sale = self.client.get(
            f'/products/{product_id}',
            headers={'Authorization': f'Bearer {admin_token}'},
        )
        self.assertEqual(product_after_sale.status_code, 200)
        self.assertEqual(product_after_sale.json()['stockQuantity'], 0)
        self.assertEqual(product_after_sale.json()['status'], 'out_of_stock')

        blocked_sale = self.client.post(
            '/sales/transactions',
            headers={'Authorization': f'Bearer {analyst_token}'},
            json={
                'productId': product_id,
                'quantity': 1,
                'unitPrice': 15.0,
                'customerName': 'Blocked Buyer',
                'saleDateTime': '2026-07-17T12:10:00',
                'salesChannel': 'Online',
                'paymentMethod': 'Card',
                'discountAmount': 0,
                'taxAmount': 0,
            },
        )
        self.assertEqual(blocked_sale.status_code, 400)
        self.assertIn('Inactive product', blocked_sale.json()['detail'])

    def test_discount_cannot_exceed_total_product_value(self):
        admin_token = self._login('admin@retailpulse.com')
        analyst_token = self._login('analyst@retailpulse.com')

        suffix = uuid.uuid4().hex[:6]
        category_id = self._create_category(admin_token, f'Discount {suffix}')
        product_id = self._create_product(admin_token, category_id, f'DSC-{suffix}', stock=5)

        response = self.client.post(
            '/sales/transactions',
            headers={'Authorization': f'Bearer {analyst_token}'},
            json={
                'productId': product_id,
                'quantity': 2,
                'unitPrice': 15.0,
                'customerName': 'Discount Buyer',
                'saleDateTime': '2026-07-17T13:00:00',
                'salesChannel': 'Online',
                'paymentMethod': 'Card',
                'discountAmount': 31,
                'taxAmount': 0,
            },
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()['detail'], 'Discount cannot exceed total product value')

    def test_sales_search_filter_and_sort(self):
        admin_token = self._login('admin@retailpulse.com')
        analyst_token = self._login('analyst@retailpulse.com')

        suffix = uuid.uuid4().hex[:6]
        category_id = self._create_category(admin_token, f'Filter {suffix}')
        product_id = self._create_product(admin_token, category_id, f'FLT-{suffix}', stock=10)

        first = self.client.post(
            '/sales/transactions',
            headers={'Authorization': f'Bearer {analyst_token}'},
            json={
                'productId': product_id,
                'quantity': 1,
                'unitPrice': 15.0,
                'customerName': f'Alpha Buyer {suffix}',
                'saleDateTime': '2026-07-17T09:00:00',
                'salesChannel': 'Online',
                'paymentMethod': 'Card',
                'discountAmount': 0,
                'taxAmount': 0,
            },
        )
        self.assertEqual(first.status_code, 200)

        second = self.client.post(
            '/sales/transactions',
            headers={'Authorization': f'Bearer {analyst_token}'},
            json={
                'productId': product_id,
                'quantity': 2,
                'unitPrice': 20.0,
                'customerName': f'Beta Buyer {suffix}',
                'saleDateTime': '2026-07-18T09:00:00',
                'salesChannel': 'In-Store',
                'paymentMethod': 'Cash',
                'discountAmount': 0,
                'taxAmount': 0,
            },
        )
        self.assertEqual(second.status_code, 200)

        searched = self.client.get(
            f'/sales/transactions?q=Alpha%20Buyer%20{suffix}',
            headers={'Authorization': f'Bearer {analyst_token}'},
        )
        self.assertEqual(searched.status_code, 200)
        self.assertEqual(len(searched.json()), 1)
        self.assertEqual(searched.json()[0]['customerName'], f'Alpha Buyer {suffix}')

        product_search = self.client.get(
            f'/sales/transactions?q=Product%20FLT-{suffix}',
            headers={'Authorization': f'Bearer {analyst_token}'},
        )
        self.assertEqual(product_search.status_code, 200)
        self.assertGreaterEqual(len(product_search.json()), 2)

        filtered = self.client.get(
            f'/sales/transactions?dateFrom=2026-07-18T00:00:00Z&dateTo=2026-07-18T23:59:59Z&categoryId={category_id}&salesChannel=In-Store&paymentMethod=Cash',
            headers={'Authorization': f'Bearer {analyst_token}'},
        )
        self.assertEqual(filtered.status_code, 200)
        self.assertEqual(len(filtered.json()), 1)
        self.assertEqual(filtered.json()[0]['customerName'], f'Beta Buyer {suffix}')

        sorted_response = self.client.get(
            '/sales/transactions?sortBy=total&sortOrder=asc',
            headers={'Authorization': f'Bearer {analyst_token}'},
        )
        self.assertEqual(sorted_response.status_code, 200)
        totals = [item['totalAmount'] for item in sorted_response.json()]
        self.assertEqual(totals, sorted(totals))


if __name__ == '__main__':
    unittest.main()
