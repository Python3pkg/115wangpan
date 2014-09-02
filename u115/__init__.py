# -*- coding: utf-8 -*-
import humanize
import requests
import time
from hashlib import sha1
import pdb
import utils

USER_AGENT = 'Mozilla/4.0 (compatible; MSIE 6.0; Windows NT 5.1)'


class RequestHandler(object):
    def __init__(self):
        self.session = requests.Session()
        self.session.headers['User-Agent'] = USER_AGENT

    def get(self, url, params=None):
        r = self.session.get(url, params=params)
        return self._response_parser(r, expect_json=False)

    def post(self, url, data, params=None):
        r = self.session.post(url, data=data, params=params)
        return self._response_parser(r, expect_json=False)

    def send(self, request):
        """Send a formatted API request"""
        r = self.session.request(method=request.method,
                                 url=request.url,
                                 params=request.params,
                                 data=request.data)
        return self._response_parser(r)

    def _response_parser(self, r, expect_json=True):
        """
        :param r: a response object of the Requests library
        :param expect_json: if True, raise APIError if response is not in JSON
            format
        """
        if r.ok:
            try:
                j = r.json()
                return Response(j.get('state'), j)
            except ValueError:
                # No JSON-encoded data returned
                if expect_json:
                    raise APIError('Invalid API access.')
                return Response(False, r.content)
        else:
            r.raise_for_status()


class Request(object):
    """Formatted API request class"""
    def __init__(self, url, method='GET', params=None, data=None):
        self.url = url
        self.method = method
        self.params = params
        self.data = data


class Response(object):
    def __init__(self, state, content):
        self.state = state
        self.content = content


class API(object):
    num_tasks_per_page = 30

    def __init__(self):
        self.passport = None
        self.http = RequestHandler()
        self.signatures = {}

    def login(self, username, password):
        passport = Passport(username, password)
        r = self.http.post(passport.login_url, passport.form)
        # Login success
        if r.state is True:
            # Bind this passport to API
            self.passport = passport
            passport.data = r.content['data']
            passport.user_id = r.content['data']['USER_ID']
        else:
            msg = None
            if 'err_name' in r.content:
                if r.content['err_name'] == 'account':
                    msg = 'Account does not exist.'
                elif r.content['err_name'] == 'passwd':
                    msg = 'Password is incorrect.'
            error = APIError(msg)
            raise error

    def has_logged_in(self):
        if self.passport is not None and self.passport.user_id is not None:
            params = {'user_id': self.passport.user_id}
            r = self.http.get(self.passport.checkpoint_url, params=params)
            if r.state is False:
                return True
        return False

    def logout(self):
        self.http.get(self.passport.logout_url)

    def _req_offline_space(self):
        """Required before accessing lixian tasks"""
        url = 'http://115.com/'
        params = {'ct': 'offline', 'ac': 'space', '_': utils.get_timestamp(13)}
        req = Request(url=url, params=params)
        r = self.http.send(req)
        if r.state:
            self.signatures['offline_space'] = r.content['sign']

    def _req_lixian_task_lists(self, page=1):
        url = 'http://115.com/lixian/'
        params = {'ct': 'lixian', 'ac': 'task_lists'}
        if 'offline_space' not in self.signatures:
            self._req_offline_space()
        data = {
            'page': page,
            'uid': self.passport.user_id,
            'sign': self.signatures['offline_space'],
            'time': utils.get_timestamp(10),
        }
        req = Request(method='POST', url=url, params=params, data=data)
        res = self.http.send(req)
        if res.state:
            return res.content['tasks']

    def _load_tasks(self, count, page=1, tasks=None):
        if tasks is None:
            tasks = []
        loaded_tasks = map(instantiate_task,
                           self._req_lixian_task_lists(page)[:count])
        if count <= self.num_tasks_per_page:
            return tasks + loaded_tasks
        else:
            return self._load_tasks(count - 30, page + 1, loaded_tasks + tasks)

    def get_tasks(self, count=30):
        return self._load_tasks(count)

    def add_task_bt(self):
        """
        Added a new BT task
        TODO:
            ac=get_id&torrent=1: get cid
            upload?debug: upload torrent file
            ac=torrent: torrent list
            ac=add_task_bt: send selected files

        """
        pass

    def add_task_url(self):
        """Added a new URL task (VIP only)"""
        pass

    def delete_task(self):
        pass


class Base(object):
    def __repr__(self):
        try:
            u = self.__str__()
        except (UnicodeEncodeError, UnicodeDecodeError):
            u = '[Bad Unicode data]'
        repr_type = type(u)
        return repr_type('<%s: %s>' % (self.__class__.__name__, u))

    def __str__(self):
        if hasattr(self, '__unicode__'):
            return unicode(self).encode('utf-8')
        return '%s object' % self.__class__.__name__


class Passport(Base):
    login_url = 'http://passport.115.com/?ct=login&ac=ajax&is_ssl=1'
    logout_url = 'http://passport.115.com/?ac=logout'
    checkpoint_url = 'http://passport.115.com/?ct=ajax&ac=ajax_check_point'

    def __init__(self, username, password):
        self.username = username
        self.password = password
        self.form = self._form()
        self.user_id = None
        self.data = None

    def _form(self):
        vcode = self._vcode()
        f = {
            'login[ssoent]': 'A1',
            'login[version]': '2.0',
            'login[ssoext]': vcode,
            'login[ssoln]': self.username,
            'login[ssopw]': self._ssopw(vcode),
            'login[ssovcode]': vcode,
            'login[safe]': '1',
            'login[time]': '0',
            'login[safe_login]': '0',
            'goto': 'http://115.com/',
        }
        return f

    def _vcode(self):
        s = '%.6f' % time.time()
        whole, frac = map(int, s.split('.'))
        res = '%x%x' % (whole, frac)
        if len(res) != 13:
            print 'Not 13'
        #assert len(res) == 13
        return res

    def _ssopw(self, vcode):
        p = sha1(self.password).hexdigest()
        u = sha1(self.username).hexdigest()
        return sha1(sha1(p + u).hexdigest() + vcode.upper()).hexdigest()

    def __unicode__(self):
        return self.username


class BaseFile(Base):
    def __init__(self, cid, name):
        """
        :param cid: integer
            for file: this represents the directory it belongs to;
            for directory: this represents itself
        :param name: string, originally named `n'

        """
        self.cid = cid
        self.name = name


class File(BaseFile):
    def __init__(self, cid, name, size, file_type, thumbnail):
        super(File, self).__init__(cid, name)
        """
        :param size: integer
        :param file_type: string, originally named `ico'
        :param thumbnail: string, URL
        """
        self.size = size
        self.file_type = file_type
        self.thumbnail = thumbnail


class Directory(BaseFile):
    def __init__(self, cid, name, pid):
        super(Directory, self).__init__(cid, name)
        """
        :param pid: integer, represents the parent directory it belongs to

        """
        self.pid = pid

    def list(self, order='user_ptime', offset=0, limit=30, asc=False):
        """
        Exhaustive params:
            aid: 1
            o: user_ptime
            asc: 0
            offset: 1
            show_dir: 0
            limit: 2
            code:
            scid:
            snap: 0
            natsort: 1
            source:
        Implemented params:
            :param order: string, originally named `o'
            :param offset: integer
            :param limit: integer
            :param asc: boolean
        """


class Task(Directory):
    def __init__(self, add_time, file_id, info_hash, last_update, left_time,
                 move, name, peers, percent_done, rate_download, size, status,
                 cid, pid):
        super(Task, self).__init__(cid, name, pid)

        """
        :param add_time: integer to datetiem object
        :param file_id: string, equivalent to `cid' in File of directory type
        :param info_hash: string
        :param last_update: integer to datetime object
        :param left_time: integer
        :param move: integer
        :param name: string
        :param peers: integer
        :param percent_done: integer (<=100), originally named `percentDone'
        :param rate_download: integer, originally named `rateDownload'
        :param size: integer
        :param status: integer
        """
        self.add_time = utils.get_utcdatetime(add_time)
        self.file_id = file_id
        self.info_hash = info_hash
        self.last_update = utils.get_utcdatetime(last_update)
        self.left_time = left_time
        self.move = move
        self.peers = peers
        self.percent_done = percent_done
        self.rate_download = rate_download
        self.size = size
        self.size_human = humanize.naturalsize(size, binary=True)
        self.status = status

    def __unicode__(self):
        return self.name


def instantiate_task(kwargs):
    """Create a Task object from raw kwargs

    rateDownload => rate_download
    percentDone => percent_done
    """
    kwargs['rate_download'] = kwargs['rateDownload']
    kwargs['percent_done'] = kwargs['percentDone']
    kwargs['cid'] = kwargs['file_id']
    kwargs['pid'] = None
    del kwargs['rateDownload']
    del kwargs['percentDone']
    return Task(**kwargs)


class APIError(Exception):
    pass
