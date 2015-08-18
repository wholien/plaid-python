import os
import warnings

from plaid.requester import (
    delete_request,
    get_request,
    http_request,
    patch_request,
    post_request
)
from plaid.utils import json, urljoin
from plaid.errors import UnauthorizedError


def inject_url(path):
    '''
    Produces a decorator which injects a url as
    the first argument to the decorated function

    `path`         str
    '''
    def decorator(func):
        def inner_func(self, *args, **kwargs):
            url = urljoin(self.base_url, self.ENDPOINTS[path])
            return func(self, url, *args, **kwargs)
        return inner_func
    return decorator


def inject_credentials(func):
    '''
    Decorator which injects a credentials object
    containing client_id, secret, and access_token
    as the first argument to the decorated function

    `func`         function
    '''

    def inner_func(self, *args, **kwargs):
        if not hasattr(self, 'access_token'):
            raise UnauthorizedError(
                '{} requires `access_token`'.format(func.__name__), 1000
            )
        else:
            credentials = {
                'client_id': self.client_id,
                'secret': self.secret,
                'access_token': self.access_token,
            }
            return func(self, credentials, *args, **kwargs)
    return inner_func


def store_access_token(func):
    '''
    Decorator which extracts the access_token from valid responses
    and stores it on the client instance
    `func`         function
    '''

    def inner_func(self, *args, **kwargs):
        response = func(self, *args, **kwargs)
        if response.ok:
            json_data = json.loads(response.content)
            self.access_token = json_data.get(
                'access_token',
                self.access_token
            )
        return response
    return inner_func


class Client(object):
    '''
    Python Plain API v2 client https://plaid.com/
    See official documentation at: https://plaid.com/docs
    '''
    base_url = os.environ.get('PLAID_HOST', 'https://tartan.plaid.com')
    suppress_http_errors = False
    suppress_warnings = False

    ACCOUNT_TYPES = (
        ('amex', 'American Express',),
        ('bofa', 'Bank of America',),
        ('chase', 'Chase',),
        ('citi', 'Citi',),
        ('wells', 'Wells Fargo',),
    )

    CATEGORY_TYPES = [
        'plaid',
        'foursquare',
        'factual',
        'amex'
    ]

    ENDPOINTS = {
        'auth': '/auth',
        'auth_get': '/auth/get',
        'auth_step': '/auth/step',
        'balance': '/balance',
        'connect': '/connect',
        'connect_get': '/connect/get',
        'connect_step': '/connect/step',
        'categories': '/categories',
        'category': '/categories/{}',
        'info_get': '/info/get',
        'institutions': '/institutions',
        'institution': '/institutions/{}',
        'upgrade': '/upgrade',
        'exchange_token': '/exchange_token',
    }

    @classmethod
    def config(kls, options):
        '''
        Configure the Client Class (Client.config({}))

        `options`         dict
            `url`          str     Fully qualified domain name (tartan or api)
            `suppress_errors`   bool    Should Plaid Errors be suppressed
            `suppress_warnings` bool    Should Plaid warnings be suppressed
        '''
        kls.base_url = options.get('url', kls.base_url)
        kls.suppress_http_errors = options.get('suppress_http_errors')
        kls.suppress_warnings = options.get('suppress_warnings')

    def __init__(self, client_id, secret, access_token=None):
        '''
        `client_id`     str     Your Plaid client ID
        `secret`        str     Your Plaid secret
        `access_token`  str     Access token for existing user (optional)
        '''
        self.client_id = client_id
        self.secret = secret
        self.access_token = access_token

        if 'tartan' in self.base_url and not self.suppress_warnings:
            warnings.warn('''
                Tartan is not intended for production usage.
                Swap out url for https://api.plaid.com
                via Client.config before switching to production
            ''')

    @store_access_token
    def _add(self, url, account_type, login, options=None):
        '''
        Add a bank account user/login to Plaid and receive an access token
        unless a 2nd level of authentication is required, in which case
        an MFA (Multi Factor Authentication) question(s) is returned

        `url`           str     Plaid endpoint url
        `account_type`  str     The type of bank account you want to sign in
                                to, must be one of the keys in `ACCOUNT_TYPES`
        `login`         dict
            `username`        str     username for the bank account
            `password`        str     The password for the bank account
            `pin`             int     (optional) pin for the bank account

        `options`       dict
            `webhook`   str         URL to hit once the account's transactions
                                    have been processed
            `mfa_list`  boolean     List all available MFA (Multi Factor
                                    Authentication) options
        '''

        return post_request(url, data={
            'client_id': self.client_id,
            'secret': self.secret,
            'type': account_type,
            'credentials': json.dumps(login),
            'options': json.dumps(
                dict(
                    {'list': True},
                    **(options if options is not None else {})
                )
            ),
        }, suppress_errors=self.suppress_http_errors)

    @store_access_token
    @inject_credentials
    def _step(self, credentials, url, method, account_type, mfa, options=None):
        '''
        Perform a MFA (Multi Factor Authentication) step with access_token.

        `method`        str     HTTP Method
        `url`           str     Plaid endpoint url

        `account_type`  str     The type of bank account you're performing MFA
                                on, must match what you used in the `connect`
                                call
        `mfa`           str     The MFA answer, e.g. an answer to q security
                                question or code sent to your phone, etc.
        `options`       dict
            `send_method`   dict    The send method your MFA answer is for,
                                    e.g. {'type': phone'}, should come from
                                    the list from the `mfa_list` option in
                                    the call
        '''
        return http_request(
            url,
            method=method,
            data=dict({
                'type': account_type,
                'mfa': mfa,
                'options': json.dumps(options if options is not None else {}),
            }, **credentials),
            suppress_errors=self.suppress_http_errors
        )

    @store_access_token
    @inject_credentials
    def _update(self, credentials, url, login):
        '''
        Similar to _add, save HTTP method, inclusion of access token,
        and absence of options / account_type
        '''
        return patch_request(
            url,
            data=dict(login, **credentials),
            suppress_errors=self.suppress_http_errors
        )

    # WRITE ENDPOINTS

    @inject_url('auth')
    def auth(self, url, *args, **kwargs):
        '''
        Add an Auth user to Plaid.
        See _add docstring for input annotation
        '''
        return self._add(url, *args, **kwargs)

    @inject_credentials
    @inject_url('auth')
    def auth_delete(self, url, credentials):
        '''
        Delete Auth user from Plaid
        '''
        return delete_request(
            url,
            data=credentials,
            suppress_errors=self.suppress_http_errors
        )

    @inject_url('auth_step')
    def auth_step(self, url, *args, **kwargs):
        '''
        MFA step associated with initially Auth-ing a user.
        See _step docstring for input annotation
        '''
        return self._step(url, 'POST', *args, **kwargs)

    @inject_url('auth')
    def auth_update(self, url, login):
        '''
        Update a user who has already authed

        `login`         dict
            `username`        str     username for the bank account
            `password`        str     The password for the bank account
            `pin`             int     (optional) pin for the bank account

        '''
        return self._update(url, login)

    @inject_url('auth_step')
    def auth_update_step(self, url, *args, **kwargs):
        '''
        MFA step associated with updating an Auth-ed user.
        See _step docstring for input annotation
        '''
        return self._step(url, 'PATCH', *args, **kwargs)

    @inject_url('connect')
    def connect(self, url, *args, **kwargs):
        '''
        Add a Connect user to Plaid.
        See _add docstring for input annotation
        '''
        return self._add(url, *args, **kwargs)

    @inject_credentials
    @inject_url('connect')
    def connect_delete(self, url, credentials):
        '''
        Delete user who has connected from Plaid
        '''
        return delete_request(
            url,
            data=credentials,
            suppress_errors=self.suppress_http_errors
        )

    @inject_url('connect_step')
    def connect_step(self, url, *args, **kwargs):
        '''
        MFA step associated with initially Connect-ing a user.
        See _step docstring for input annotation
        '''
        return self._step(url, 'POST', *args, **kwargs)

    @inject_url('connect')
    def connect_update(self, url, login):
        '''
        Update a user who has already connected

        `login`         dict
            `username`        str     username for the bank account
            `password`        str     The password for the bank account
            `pin`             int     (optional) pin for the bank account

        '''
        return self._update(url, login)

    @inject_url('connect_step')
    def connect_update_step(self, url, *args, **kwargs):
        '''
        MFA step associated with updating a Connect-ed user.
        See _step docstring for input annotation
        '''
        return self._step(url, 'PATCH', *args, **kwargs)

    @store_access_token
    @inject_url('exchange_token')
    def exchange_token(self, url, public_token):
        '''
        Only applicable to apps using the Link front-end SDK
        Exchange a Link public_token for an API access_token

        `public_token`     str    public_token returned by Link client
        '''
        return post_request(
            url,
            data={
                'client_id': self.client_id,
                'secret': self.secret,
                'public_token': public_token,
            },
            suppress_errors=self.suppress_http_errors
        )

    @store_access_token
    @inject_credentials
    @inject_url('upgrade')
    def upgrade(self, url, credentials, product):
        '''
        Upgrade account to another plaid type

        `product`     str    [auth | connect]
        '''
        return post_request(
            url,
            data=dict(credentials, upgrade_to=product),
            suppress_errors=self.suppress_http_errors
        )

    # READ ENDPOINTS
    @inject_credentials
    @inject_url('auth_get')
    def auth_get(self, url, credentials):
        '''
        Fetch accounts associated with the set access_token
        '''
        return post_request(
            url,
            data=credentials,
            suppress_errors=self.suppress_http_errors
        )

    @inject_credentials
    @inject_url('balance')
    def balance(self, url, credentials):
        '''
        Fetch the real-time balance of the user's accounts
        '''
        return get_request(
            url,
            data=credentials,
            suppress_errors=self.suppress_http_errors
        )

    @inject_credentials
    @inject_url('connect_get')
    def connect_get(self, url, credentials, opts=None):
        '''
        Fetch a list of transactions, requires `access_token`

        `options`   dict (optional)
            `pending`     bool      Fetch pending transactions (default false)
            `account`     str       Fetch transactions only from this account
            `gte`         date      Fetch transactions posted after this date
                                    (default 30 days ago)
            `lte`         date      Fetch transactions posted before this date
        '''

        return post_request(
            url,
            data=dict(
                credentials,
                **{'options': json.dumps(opts if opts is not None else {})}
            ),
            suppress_errors=self.suppress_http_errors
        )

    @inject_url('categories')
    def categories(self, url):
        '''Fetch all Plaid Categories'''
        return get_request(url, suppress_errors=self.suppress_http_errors)

    @inject_url('category')
    def category(self, url, category_id):
        '''
        Fetch a specific category

        `category_id`   str     Category id to fetch
        '''
        return get_request(
            url.format(category_id),
            suppress_errors=self.suppress_http_errors
        )

    @inject_credentials
    @inject_url('info_get')
    def info_get(self, url, credentials):
        '''
        Fetches info for a user
        '''
        return post_request(
            url,
            data=credentials,
            suppress_errors=self.suppress_http_errors
        )

    @inject_url('institutions')
    def institutions(self, url):
        '''
        Fetch all Plaid institutions
        '''
        return get_request(url, suppress_errors=self.suppress_http_errors)

    @inject_url('institution')
    def institution(self, url, institution_id):
        '''
        Fetch details for a single institution

        `institution_id`   str     Category id to fetch
        '''
        return get_request(
            url.format(institution_id),
            suppress_errors=self.suppress_http_errors
        )
