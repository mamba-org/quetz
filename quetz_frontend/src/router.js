import Vue from 'vue';
import Router from 'vue-router';

import Channels from './views/Channels.vue';
import Users from './views/Users.vue';
import ApiKeys from './views/ApiKeys';
import Packages from './views/Packages';
import Package from './views/Package';
import Jobs from './views/Jobs';
import Tasks from './views/Tasks';

import Header from './components/Header';

import CarbonComponentsVue from '@carbon/vue';
Vue.use(CarbonComponentsVue);

Vue.use(Router);

export default new Router({
  routes: [
    {
      path: '/channels',
      name: 'channels',
      component: Channels
    },
    {
      path: '/',
      name: 'root_channels',
      component: Channels
    },
    {
      path: '/users',
      name: 'users',
      component: Users
    },
    {
      path: '/api-keys',
      name: 'api-keys',
      component: ApiKeys
    },
    {
      path: '/channel/:channel_id/packages',
      name: 'packages',
      component: Packages
    },
    {
      path: '/jobs/',
      name: 'jobs',
      component: Jobs
    },
    {
      path: '/jobs/:job_id',
      name: 'tasks',
      component: Tasks
    },
    {
      path: '/channel/:channel_id/packages/:package',
      name: 'package',
      component: Package
    },
    {
      path: '/header',
      name: 'header',
      component: Header
    }
  ],
  mode: 'history'
});