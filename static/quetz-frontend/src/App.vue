<template>
  <div id="app">
    <Header />
    <cv-content id="main-content" class="container">
      <router-view />
    </cv-content>
  </div>
</template>

<script>
import Header from './components/Header';
export default {
  name: 'App',
  components: {
    Header
  }
};
</script>

<style lang="scss">
@import './styles/carbon';
</style>
