import Vue from 'vue';
import Router from 'vue-router';
import CarbonComponentsVue from '@carbon/vue';

import ChannelsView from './views/ChannelsView';
import UsersView from './views/UsersView';
import ApiKeysView from './views/ApiKeysView';
import PackagesView from './views/PackagesView';
import PackageView from './views/PackageView';
import JobsView from './views/JobsView';
import TasksView from './views/TasksView';

import HeaderComponent from './components/HeaderComponent';


Vue.use(CarbonComponentsVue);
Vue.use(Router);

export default new Router({
  routes: [
    {
      path: '/channels',
      name: 'channels',
      component: ChannelsView
    },
    {
      path: '/',
      name: 'root_channels',
      component: ChannelsView
    },
    {
      path: '/users',
      name: 'users',
      component: UsersView
    },
    {
      path: '/api-keys',
      name: 'api-keys',
      component: ApiKeysView
    },
    {
      path: '/channel/:channel_id/packages',
      name: 'packages',
      component: PackagesView
    },
    {
      path: '/jobs/',
      name: 'jobs',
      component: JobsView
    },
    {
      path: '/jobs/:job_id',
      name: 'tasks',
      component: TasksView
    },
    {
      path: '/channel/:channel_id/packages/:package',
      name: 'package',
      component: PackageView
    },
    {
      path: '/header',
      name: 'header',
      component: HeaderComponent
    }],
    mode: 'history'
});